# -*- coding: utf-8 -*-
"""
Сервис работы с заявками на ремонт (RepairOrder).

Содержит CRUD-операции, смену статуса с валидацией допустимых переходов
и ведение истории изменений статуса. Работает через ORM-модели
RepairOrder и OrderStatusHistory (models.py).

Соглашения (как в services/document_service.py):
- каждая функция открывает свою SessionLocal() и закрывает её в finally;
- изменяющие операции возвращают Tuple[bool, str] (успех, сообщение);
- при исключении делаем rollback и возвращаем текст ошибки.

Стоимость хранится и передаётся в копейках (целое число), чтобы
исключить ошибки округления float. Форматирование в рубли — на уровне
представления (format_cost).
"""

from typing import List, Optional, Tuple

from models import SessionLocal, RepairOrder, OrderStatusHistory, Ship


def format_cost(cost_kopecks: int) -> str:
    """Форматирует стоимость из копеек в строку рублей.

    Args:
        cost_kopecks: Стоимость в копейках (целое).

    Returns:
        Строка вида "1 234.56 ₽".
    """
    rub, kop = divmod(max(0, int(cost_kopecks)), 100)
    return f"{rub:,}".replace(",", " ") + f".{kop:02d} \u20bd"


def create_order(
    ship_id: int,
    work_type: str,
    user_id: int,
    cost_kopecks: int = 0,
) -> Tuple[bool, str, Optional[int]]:
    """Создаёт заявку на ремонт.

    Args:
        ship_id: ID судна (должно существовать).
        work_type: Тип/описание работ.
        user_id: Telegram ID создавшего пользователя.
        cost_kopecks: Стоимость в копейках (>= 0).

    Returns:
        Кортеж (success, message, order_id | None).
    """
    if cost_kopecks < 0:
        return False, "\u274c \u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c \u043d\u0435 \u043c\u043e\u0436\u0435\u0442 \u0431\u044b\u0442\u044c \u043e\u0442\u0440\u0438\u0446\u0430\u0442\u0435\u043b\u044c\u043d\u043e\u0439", None
    if not (work_type or "").strip():
        return False, "\u274c \u0422\u0438\u043f \u0440\u0430\u0431\u043e\u0442 \u043d\u0435 \u043c\u043e\u0436\u0435\u0442 \u0431\u044b\u0442\u044c \u043f\u0443\u0441\u0442\u044b\u043c", None

    session = SessionLocal()
    try:
        ship = session.query(Ship).filter_by(id=ship_id).first()
        if not ship:
            return False, f"\u274c \u0421\u0443\u0434\u043d\u043e id={ship_id} \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e", None
        order = RepairOrder(
            ship_id=ship_id,
            work_type=work_type.strip(),
            status="new",
            cost_kopecks=int(cost_kopecks),
            created_by=user_id,
        )
        session.add(order)
        session.flush()  # получаем order.id до commit
        session.add(OrderStatusHistory(
            order_id=order.id,
            from_status=None,
            to_status="new",
            changed_by=user_id,
        ))
        order_id = order.id
        session.commit()
        return True, f"\u2705 \u0417\u0430\u044f\u0432\u043a\u0430 \u2116{order_id} \u0441\u043e\u0437\u0434\u0430\u043d\u0430", order_id
    except Exception as e:
        session.rollback()
        return False, f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430: {str(e)}", None
    finally:
        session.close()


def get_order(order_id: int) -> Optional[RepairOrder]:
    """Возвращает заявку по ID (или None)."""
    session = SessionLocal()
    try:
        return session.query(RepairOrder).filter_by(id=order_id).first()
    finally:
        session.close()


def list_orders(
    ship_id: Optional[int] = None,
    status: Optional[str] = None,
) -> List[RepairOrder]:
    """Возвращает список заявок с опциональной фильтрацией.

    Args:
        ship_id: Фильтр по судну (опционально).
        status: Фильтр по статусу (опционально).

    Returns:
        Список RepairOrder, новые сверху.
    """
    session = SessionLocal()
    try:
        query = session.query(RepairOrder)
        if ship_id is not None:
            query = query.filter(RepairOrder.ship_id == ship_id)
        if status is not None:
            query = query.filter(RepairOrder.status == status)
        return query.order_by(RepairOrder.created_at.desc()).all()
    finally:
        session.close()


def update_cost(order_id: int, cost_kopecks: int) -> Tuple[bool, str]:
    """Обновляет стоимость заявки.

    Args:
        order_id: ID заявки.
        cost_kopecks: Новая стоимость в копейках (>= 0).

    Returns:
        Кортеж (success, message).
    """
    if cost_kopecks < 0:
        return False, "\u274c \u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c \u043d\u0435 \u043c\u043e\u0436\u0435\u0442 \u0431\u044b\u0442\u044c \u043e\u0442\u0440\u0438\u0446\u0430\u0442\u0435\u043b\u044c\u043d\u043e\u0439"
    session = SessionLocal()
    try:
        order = session.query(RepairOrder).filter_by(id=order_id).first()
        if not order:
            return False, "\u274c \u0417\u0430\u044f\u0432\u043a\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430"
        if order.status in ("closed", "cancelled"):
            return False, f"\u274c \u041d\u0435\u043b\u044c\u0437\u044f \u043c\u0435\u043d\u044f\u0442\u044c \u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c \u0437\u0430\u044f\u0432\u043a\u0438 \u0432 \u0441\u0442\u0430\u0442\u0443\u0441\u0435 {order.status}"
        order.cost_kopecks = int(cost_kopecks)
        session.commit()
        return True, f"\u2705 \u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0430: {format_cost(cost_kopecks)}"
    except Exception as e:
        session.rollback()
        return False, f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430: {str(e)}"
    finally:
        session.close()


def change_status(order_id: int, new_status: str, user_id: int) -> Tuple[bool, str]:
    """Меняет статус заявки с проверкой допустимости перехода.

    Переход считается допустимым, если он присутствует в
    RepairOrder.TRANSITIONS для текущего статуса. Смена статуса и запись
    в историю выполняются в одной транзакции, поэтому история не может
    разойтись с фактическим статусом.

    Args:
        order_id: ID заявки.
        new_status: Целевой статус.
        user_id: Telegram ID пользователя, инициировавшего смену.

    Returns:
        Кортеж (success, message).
    """
    if new_status not in RepairOrder.STATUSES:
        return False, (
            f"\u274c \u041d\u0435\u0434\u043e\u043f\u0443\u0441\u0442\u0438\u043c\u044b\u0439 \u0441\u0442\u0430\u0442\u0443\u0441 '{new_status}'. "
            f"\u0414\u043e\u043f\u0443\u0441\u0442\u0438\u043c\u044b\u0435: {', '.join(RepairOrder.STATUSES)}"
        )
    session = SessionLocal()
    try:
        order = session.query(RepairOrder).filter_by(id=order_id).first()
        if not order:
            return False, "\u274c \u0417\u0430\u044f\u0432\u043a\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430"

        current = order.status
        if new_status == current:
            return False, f"\u2139\ufe0f \u0417\u0430\u044f\u0432\u043a\u0430 \u0443\u0436\u0435 \u0432 \u0441\u0442\u0430\u0442\u0443\u0441\u0435 '{current}'"

        allowed = RepairOrder.TRANSITIONS.get(current, set())
        if new_status not in allowed:
            allowed_str = ", ".join(sorted(allowed)) if allowed else "\u043d\u0435\u0442 (\u0444\u0438\u043d\u0430\u043b\u044c\u043d\u044b\u0439 \u0441\u0442\u0430\u0442\u0443\u0441)"
            return False, (
                f"\u274c \u041d\u0435\u0434\u043e\u043f\u0443\u0441\u0442\u0438\u043c\u044b\u0439 \u043f\u0435\u0440\u0435\u0445\u043e\u0434 '{current}' \u2192 '{new_status}'. "
                f"\u0414\u043e\u0441\u0442\u0443\u043f\u043d\u043e \u0438\u0437 '{current}': {allowed_str}"
            )

        order.status = new_status
        session.add(OrderStatusHistory(
            order_id=order.id,
            from_status=current,
            to_status=new_status,
            changed_by=user_id,
        ))
        session.commit()
        return True, f"\u2705 \u0421\u0442\u0430\u0442\u0443\u0441 \u0437\u0430\u044f\u0432\u043a\u0438 \u2116{order_id}: {current} \u2192 {new_status}"
    except Exception as e:
        session.rollback()
        return False, f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430: {str(e)}"
    finally:
        session.close()


def delete_order(order_id: int, user_id: int, admin_ids=None) -> Tuple[bool, str]:
    """Удаляет заявку (вместе с историей статусов через каскад).

    Удалять может только администратор — заявка это управленческая
    сущность, случайное удаление недопустимо.

    Args:
        order_id: ID заявки.
        user_id: Telegram ID пользователя.
        admin_ids: Список ID администраторов.

    Returns:
        Кортеж (success, message).
    """
    admin_ids = admin_ids or []
    if user_id not in admin_ids:
        return False, "\U0001f6ab \u0423\u0434\u0430\u043b\u044f\u0442\u044c \u0437\u0430\u044f\u0432\u043a\u0438 \u043c\u043e\u0433\u0443\u0442 \u0442\u043e\u043b\u044c\u043a\u043e \u0430\u0434\u043c\u0438\u043d\u044b"
    session = SessionLocal()
    try:
        order = session.query(RepairOrder).filter_by(id=order_id).first()
        if not order:
            return False, "\u274c \u0417\u0430\u044f\u0432\u043a\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430"
        session.delete(order)
        session.commit()
        return True, f"\u2705 \u0417\u0430\u044f\u0432\u043a\u0430 \u2116{order_id} \u0443\u0434\u0430\u043b\u0435\u043d\u0430"
    except Exception as e:
        session.rollback()
        return False, f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430: {str(e)}"
    finally:
        session.close()


def get_status_history(order_id: int) -> List[OrderStatusHistory]:
    """Возвращает историю изменений статуса заявки (хронологически)."""
    session = SessionLocal()
    try:
        return (
            session.query(OrderStatusHistory)
            .filter(OrderStatusHistory.order_id == order_id)
            .order_by(OrderStatusHistory.changed_at.asc())
            .all()
        )
    finally:
        session.close()
