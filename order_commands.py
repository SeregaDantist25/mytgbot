# -*- coding: utf-8 -*-
"""
Команды управления заявками на ремонт (RepairOrder).
Импортируется и регистрируется в bot.py.

Команды:
  /orders [ship_id]                 — список заявок (все или по судну)
  /order <order_id>                 — карточка заявки + история статусов
  /order_new <ship_id> <тип работ>  — создать заявку
  /order_cost <order_id> <рубли>    — задать стоимость (в рублях)
  /order_status <order_id> <статус> — сменить статус
  /order_del <order_id>             — удалить заявку (только админ)

Стоимость пользователь вводит в рублях (может с копейками через точку),
внутри хранится в копейках.
"""

from utils.decorators import require_role
from services import order_service


# Роли, которым разрешено работать с заявками (заказчик исключён намеренно).
_ORDER_ROLES = ["engineer", "engineer_technologist", "director", "builder"]


def _parse_rubles_to_kopecks(raw: str) -> int:
    """Преобразует строку рублей ('1500' или '1500.50') в копейки (int).

    Raises:
        ValueError: если строка не является корректной суммой.
    """
    raw = raw.replace(" ", "").replace(",", ".")
    rubles = round(float(raw), 2)
    if rubles < 0:
        raise ValueError("negative")
    return int(round(rubles * 100))


def register_order_commands(bot, admin_ids):
    """Регистрирует команды управления заявками на ремонт."""
    admin_ids = admin_ids or []

    @bot.message_handler(commands=['orders'])
    @require_role(_ORDER_ROLES)
    def cmd_orders(message):
        """Список заявок: /orders [ship_id]"""
        parts = message.text.split()
        ship_id = None
        if len(parts) >= 2:
            try:
                ship_id = int(parts[1])
            except ValueError:
                bot.reply_to(message, "\u274c ship_id \u0434\u043e\u043b\u0436\u0435\u043d \u0431\u044b\u0442\u044c \u0447\u0438\u0441\u043b\u043e\u043c")
                return
        orders = order_service.list_orders(ship_id=ship_id)
        if not orders:
            bot.reply_to(message, "\U0001f4ed \u0417\u0430\u044f\u0432\u043e\u043a \u043d\u0435\u0442")
            return
        lines = ["\U0001f4cb \u0417\u0430\u044f\u0432\u043a\u0438 \u043d\u0430 \u0440\u0435\u043c\u043e\u043d\u0442:"]
        for o in orders:
            lines.append(
                f"\u2116{o.id} \u2022 \u0441\u0443\u0434\u043d\u043e {o.ship_id} \u2022 {o.status} \u2022 "
                f"{order_service.format_cost(o.cost_kopecks)}\n   {o.work_type or '\u2014'}"
            )
        bot.reply_to(message, "\n".join(lines))

    @bot.message_handler(commands=['order'])
    @require_role(_ORDER_ROLES)
    def cmd_order(message):
        """Карточка заявки: /order <order_id>"""
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "\U0001f4dd \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /order <order_id>")
            return
        try:
            order_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "\u274c order_id \u0434\u043e\u043b\u0436\u0435\u043d \u0431\u044b\u0442\u044c \u0447\u0438\u0441\u043b\u043e\u043c")
            return
        order = order_service.get_order(order_id)
        if not order:
            bot.reply_to(message, "\u274c \u0417\u0430\u044f\u0432\u043a\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430")
            return
        history = order_service.get_status_history(order_id)
        hist_lines = [
            f"   {h.from_status or '\u2014'} \u2192 {h.to_status} ({h.changed_at:%Y-%m-%d %H:%M})"
            for h in history
        ]
        text = (
            f"\U0001f4c4 \u0417\u0430\u044f\u0432\u043a\u0430 \u2116{order.id}\n"
            f"\u0421\u0443\u0434\u043d\u043e: {order.ship_id}\n"
            f"\u0420\u0430\u0431\u043e\u0442\u044b: {order.work_type or '\u2014'}\n"
            f"\u0421\u0442\u0430\u0442\u0443\u0441: {order.status}\n"
            f"\u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c: {order_service.format_cost(order.cost_kopecks)}\n"
            f"\u0418\u0441\u0442\u043e\u0440\u0438\u044f \u0441\u0442\u0430\u0442\u0443\u0441\u043e\u0432:\n" + ("\n".join(hist_lines) or "   \u2014")
        )
        bot.reply_to(message, text)

    @bot.message_handler(commands=['order_new'])
    @require_role(_ORDER_ROLES)
    def cmd_order_new(message):
        """Создать заявку: /order_new <ship_id> <тип работ>"""
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            bot.reply_to(message, "\U0001f4dd \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /order_new <ship_id> <\u0442\u0438\u043f \u0440\u0430\u0431\u043e\u0442>")
            return
        try:
            ship_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "\u274c ship_id \u0434\u043e\u043b\u0436\u0435\u043d \u0431\u044b\u0442\u044c \u0447\u0438\u0441\u043b\u043e\u043c")
            return
        ok, msg, _ = order_service.create_order(
            ship_id=ship_id, work_type=parts[2], user_id=message.from_user.id
        )
        bot.reply_to(message, msg)

    @bot.message_handler(commands=['order_cost'])
    @require_role(_ORDER_ROLES)
    def cmd_order_cost(message):
        """Задать стоимость: /order_cost <order_id> <рубли>"""
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "\U0001f4dd \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /order_cost <order_id> <\u0440\u0443\u0431\u043b\u0438>")
            return
        try:
            order_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "\u274c order_id \u0434\u043e\u043b\u0436\u0435\u043d \u0431\u044b\u0442\u044c \u0447\u0438\u0441\u043b\u043e\u043c")
            return
        try:
            kopecks = _parse_rubles_to_kopecks(parts[2])
        except ValueError:
            bot.reply_to(message, "\u274c \u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c \u0434\u043e\u043b\u0436\u043d\u0430 \u0431\u044b\u0442\u044c \u043d\u0435\u043e\u0442\u0440\u0438\u0446\u0430\u0442\u0435\u043b\u044c\u043d\u044b\u043c \u0447\u0438\u0441\u043b\u043e\u043c (\u043d\u0430\u043f\u0440. 1500 \u0438\u043b\u0438 1500.50)")
            return
        ok, msg = order_service.update_cost(order_id, kopecks)
        bot.reply_to(message, msg)

    @bot.message_handler(commands=['order_status'])
    @require_role(_ORDER_ROLES)
    def cmd_order_status(message):
        """Сменить статус: /order_status <order_id> <статус>"""
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(
                message,
                "\U0001f4dd \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /order_status <order_id> <\u0441\u0442\u0430\u0442\u0443\u0441>\n"
                "\u0421\u0442\u0430\u0442\u0443\u0441\u044b: new, in_progress, done, closed, cancelled"
            )
            return
        try:
            order_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "\u274c order_id \u0434\u043e\u043b\u0436\u0435\u043d \u0431\u044b\u0442\u044c \u0447\u0438\u0441\u043b\u043e\u043c")
            return
        ok, msg = order_service.change_status(order_id, parts[2], message.from_user.id)
        bot.reply_to(message, msg)

    @bot.message_handler(commands=['order_del'])
    @require_role(['engineer', 'director'])
    def cmd_order_del(message):
        """Удалить заявку (только админ): /order_del <order_id>"""
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "\U0001f4dd \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435: /order_del <order_id>")
            return
        try:
            order_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "\u274c order_id \u0434\u043e\u043b\u0436\u0435\u043d \u0431\u044b\u0442\u044c \u0447\u0438\u0441\u043b\u043e\u043c")
            return
        ok, msg = order_service.delete_order(order_id, message.from_user.id, admin_ids)
        bot.reply_to(message, msg)
