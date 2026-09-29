"""Очередь задач питомца.

Осознанно пустой пакет: если реэкспортировать здесь `task_manager`, имя
`tasks.task_manager` перестаёт указывать на модуль и начинает указывать на
экземпляр — из-за этого ломаются подмены в тестах и `import tasks.task_manager as ...`.
Импортируйте явно: `from tasks.task_manager import task_manager`.
"""
