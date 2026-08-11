# -*- coding: utf-8 -*-
"""
Команды для управления документами (версионирование).
Импортируется в bot.py.
"""

def register_document_commands(bot, ADMIN_IDS, handle_document_approve, handle_document_archive, handle_document_delete):
    """Регистрирует команды управления документами."""
    
    @bot.message_handler(commands=['approve_doc'])
    def cmd_approve_doc(message):
        """Утвердить черновик: /approve_doc <doc_id>"""
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "📝 Использование: /approve_doc <doc_id>")
            return
        
        try:
            doc_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ doc_id должен быть числом")
            return
        
        success, msg = handle_document_approve(doc_id, message.chat.id)
        bot.reply_to(message, msg)
    
    
    @bot.message_handler(commands=['archive_doc'])
    def cmd_archive_doc(message):
        """Архивировать документ: /archive_doc <doc_id>"""
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "📝 Использование: /archive_doc <doc_id>")
            return
        
        try:
            doc_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ doc_id должен быть числом")
            return
        
        success, msg = handle_document_archive(doc_id, message.chat.id)
        bot.reply_to(message, msg)
    
    
    @bot.message_handler(commands=['delete_doc'])
    def cmd_delete_doc(message):
        """Удалить документ: /delete_doc <doc_id>"""
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "📝 Использование: /delete_doc <doc_id>")
            return
        
        try:
            doc_id = int(parts[1])
        except ValueError:
            bot.reply_to(message, "❌ doc_id должен быть числом")
            return
        
        success, msg = handle_document_delete(doc_id, message.chat.id)
        bot.reply_to(message, msg)
