# -*- coding: utf-8 -*-
"""
Обработчики для работы с документами через StatesGroup.
Включает загрузку, замену и удаление документов.
"""

from telebot import types
from document_states import DocumentStates
from models import SessionLocal, Document, StatementItem
from file_storage import storage
import os


def register_document_handlers(bot):
    """Регистрирует обработчики документов в боте."""
    
    # ========================================================================
    # Загрузка документа
    # ========================================================================
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("upload_"))
    def handle_upload_button(call):
        """Обработчик кнопки 'Загрузить документ'."""
        try:
            item_id = int(call.data.split("_")[1])
            
            # Проверяем, что пункт существует
            session = SessionLocal()
            item = session.query(StatementItem).filter_by(id=item_id).first()
            session.close()
            
            if not item:
                bot.answer_callback_query(call.id, "❌ Пункт не найден", show_alert=True)
                return
            
            # Переходим в состояние выбора категории
            bot.set_state(call.from_user.id, DocumentStates.waiting_for_category)
            
            # Сохраняем item_id в данные пользователя
            with bot.retrieve_data(call.from_user.id) as data:
                data['item_id'] = item_id
            
            # Показываем клавиатуру с категориями
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("📋 Акты дефектации", callback_data="cat_defect_act"))
            keyboard.add(types.InlineKeyboardButton("⚙️ АВР", callback_data="cat_avr"))
            keyboard.add(types.InlineKeyboardButton("📄 Прочее", callback_data="cat_other"))
            
            bot.edit_message_text(
                "📤 Выберите категорию документа:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )
            
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("cat_"), state=DocumentStates.waiting_for_category)
    def handle_category_selection(call):
        """Обработчик выбора категории."""
        try:
            category = call.data.split("_", 1)[1]
            
            with bot.retrieve_data(call.from_user.id) as data:
                data['category'] = category
            
            # Переходим в состояние ожидания файла
            bot.set_state(call.from_user.id, DocumentStates.waiting_for_file)
            
            bot.edit_message_text(
                "📤 Отправьте документ (DOCX, XLSX, PDF):",
                call.message.chat.id,
                call.message.message_id
            )
            
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    
    
    @bot.message_handler(state=DocumentStates.waiting_for_file, content_types=['document'])
    def handle_file_upload(message):
        """Обработчик загрузки файла."""
        try:
            with bot.retrieve_data(message.from_user.id) as data:
                item_id = data.get('item_id')
                category = data.get('category')
            
            if not item_id or not category:
                bot.reply_to(message, "❌ Ошибка: потеряны данные сессии")
                return
            
            # Получаем информацию о файле
            file_info = bot.get_file(message.document.file_id)
            file_name = message.document.file_name
            file_type = os.path.splitext(file_name)[1].lower()
            
            # Проверяем расширение файла
            allowed_types = ['.docx', '.xlsx', '.pdf']
            if file_type not in allowed_types:
                bot.reply_to(message, f"❌ Недопустимый тип файла. Допустимые: {', '.join(allowed_types)}")
                return
            
            # Скачиваем файл
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Сохраняем в хранилище
            file_path = storage.save_file(
                file_name=file_name,
                file_content=downloaded_file,
                item_id=item_id,
                category=category,
                user_id=message.from_user.id
            )
            
            # Выходим из состояния
            bot.delete_state(message.from_user.id)
            
            bot.reply_to(message, f"✅ Документ загружен успешно!\n📁 {file_name}")
            
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка при загрузке: {str(e)}")
    
    
    # ========================================================================
    # Замена документа
    # ========================================================================
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("replace_"))
    def handle_replace_button(call):
        """Обработчик кнопки 'Заменить'."""
        try:
            doc_id = int(call.data.split("_")[1])
            
            # Проверяем, что документ существует и это draft
            session = SessionLocal()
            doc = session.query(Document).filter_by(id=doc_id).first()
            session.close()
            
            if not doc:
                bot.answer_callback_query(call.id, "❌ Документ не найден", show_alert=True)
                return
            
            if doc.status != "draft":
                bot.answer_callback_query(call.id, "❌ Можно заменять только черновики", show_alert=True)
                return
            
            # Переходим в состояние ожидания замены
            bot.set_state(call.from_user.id, DocumentStates.waiting_for_replacement)
            
            with bot.retrieve_data(call.from_user.id) as data:
                data['doc_id'] = doc_id
                data['item_id'] = doc.item_id
                data['category'] = doc.category
            
            bot.edit_message_text(
                "📤 Отправьте новый документ для замены:",
                call.message.chat.id,
                call.message.message_id
            )
            
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    
    
    @bot.message_handler(state=DocumentStates.waiting_for_replacement, content_types=['document'])
    def handle_file_replacement(message):
        """Обработчик замены файла."""
        try:
            with bot.retrieve_data(message.from_user.id) as data:
                doc_id = data.get('doc_id')
                item_id = data.get('item_id')
                category = data.get('category')
            
            if not doc_id or not item_id or not category:
                bot.reply_to(message, "❌ Ошибка: потеряны данные сессии")
                return
            
            # Получаем информацию о файле
            file_info = bot.get_file(message.document.file_id)
            file_name = message.document.file_name
            file_type = os.path.splitext(file_name)[1].lower()
            
            # Проверяем расширение файла
            allowed_types = ['.docx', '.xlsx', '.pdf']
            if file_type not in allowed_types:
                bot.reply_to(message, f"❌ Недопустимый тип файла. Допустимые: {', '.join(allowed_types)}")
                return
            
            # Скачиваем файл
            downloaded_file = bot.download_file(file_info.file_path)
            
            # Удаляем старый файл
            session = SessionLocal()
            doc = session.query(Document).filter_by(id=doc_id).first()
            if doc and doc.file_ref:
                try:
                    storage.delete_file(doc.file_ref)
                except:
                    pass  # Игнорируем ошибки удаления
            
            # Сохраняем новый файл с тем же item_id и category, но новым содержимым
            file_path = storage.save_file(
                file_name=file_name,
                file_content=downloaded_file,
                item_id=item_id,
                category=category,
                user_id=message.from_user.id,
                replace_doc_id=doc_id  # Указываем, что это замена
            )
            
            # Обновляем документ в БД
            doc.file_ref = file_path
            doc.file_type = file_type
            session.commit()
            session.close()
            
            # Выходим из состояния
            bot.delete_state(message.from_user.id)
            
            bot.reply_to(message, f"✅ Документ заменён успешно!\n📁 {file_name}")
            
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка при замене: {str(e)}")
    
    
    # ========================================================================
    # Удаление документа
    # ========================================================================
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
    def handle_delete_button(call):
        """Обработчик кнопки 'Удалить'."""
        try:
            doc_id = int(call.data.split("_")[1])
            
            # Проверяем, что документ существует
            session = SessionLocal()
            doc = session.query(Document).filter_by(id=doc_id).first()
            session.close()
            
            if not doc:
                bot.answer_callback_query(call.id, "❌ Документ не найден", show_alert=True)
                return
            
            # Переходим в состояние подтверждения
            bot.set_state(call.from_user.id, DocumentStates.confirming_delete)
            
            with bot.retrieve_data(call.from_user.id) as data:
                data['doc_id'] = doc_id
            
            # Показываем подтверждение
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{doc_id}"),
                types.InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_delete_{doc_id}")
            )
            
            bot.edit_message_text(
                f"⚠️ Вы уверены, что хотите удалить документ v{doc.version}?",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )
            
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_delete_"), state=DocumentStates.confirming_delete)
    def handle_delete_confirmation(call):
        """Обработчик подтверждения удаления."""
        try:
            doc_id = int(call.data.split("_")[2])
            
            # Удаляем документ
            session = SessionLocal()
            doc = session.query(Document).filter_by(id=doc_id).first()
            
            if doc:
                # Удаляем файл из хранилища
                try:
                    storage.delete_file(doc.file_ref)
                except:
                    pass  # Игнорируем ошибки удаления файла
                
                # Удаляем запись из БД
                session.delete(doc)
                session.commit()
            
            session.close()
            
            # Выходим из состояния
            bot.delete_state(call.from_user.id)
            
            bot.edit_message_text(
                "✅ Документ удалён успешно!",
                call.message.chat.id,
                call.message.message_id
            )
            
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_delete_"), state=DocumentStates.confirming_delete)
    def handle_delete_cancellation(call):
        """Обработчик отмены удаления."""
        try:
            doc_id = int(call.data.split("_")[2])
            
            # Выходим из состояния
            bot.delete_state(call.from_user.id)
            
            bot.edit_message_text(
                "❌ Удаление отменено",
                call.message.chat.id,
                call.message.message_id
            )
            
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
