# ui/history_manager.py
import json
import os
from PySide6.QtCore import QObject, Signal, QDateTime, Qt, QStandardPaths

class HistoryManager(QObject):
    event_added = Signal(dict)
    undo_requested = Signal(object)

    _instance = None
    MAX_EVENTS = 1000

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = QObject.__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        super().__init__()
        self._events = []
        self._initialized = True

        # Путь к файлу истории во временной папке
        app_data_dir = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
        # На всякий случай создаём подпапку с названием приложения
        self._storage_dir = os.path.join(app_data_dir, "DBapp")
        os.makedirs(self._storage_dir, exist_ok=True)
        self._storage_path = os.path.join(self._storage_dir, "history.json")

        # Загружаем сохранённую историю
        self._load()

    def _serialize_event(self, event: dict) -> dict:
        """Готовит событие для JSON: преобразует QDateTime в строку ISO."""
        data = event.copy()
        if isinstance(data.get("timestamp"), QDateTime):
            data["timestamp"] = data["timestamp"].toString(Qt.ISODate)
        # На случай, если timestamp уже строка (при повторной сериализации) – оставляем как есть
        return data

    def _deserialize_event(self, data: dict) -> dict:
        """Восстанавливает QDateTime из строки ISO."""
        event = data.copy()
        ts = event.get("timestamp")
        if isinstance(ts, str):
            event["timestamp"] = QDateTime.fromString(ts, Qt.ISODate)
        return event

    def _save(self):
        """Сохраняет текущую историю в JSON-файл."""
        try:
            serializable = [self._serialize_event(ev) for ev in self._events]
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
        except Exception:
            # Ошибки сохранения не должны нарушать работу приложения
            pass

    def clear(self):
        """Полностью очищает историю и удаляет файл на диске."""
        self._events.clear()
        try:
            if os.path.exists(self._storage_path):
                os.remove(self._storage_path)
        except Exception:
            pass

    def _load(self):
        if not os.path.exists(self._storage_path):
            return
        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            events = [self._deserialize_event(ev) for ev in raw]
            if len(events) > self.MAX_EVENTS:
                events = events[-self.MAX_EVENTS:]
            self._events = events
            # Сигналы здесь не излучаем, чтобы не потерять их до создания сайдбара
        except Exception:
            self._events = []

    def add_event(self, event_type: str, text: str, show_callback=None,
                  repeat_data=None, show_target=None, undo_data=None):
        event = {
            'type': event_type,
            'text': text,
            'show_callback': show_callback,
            'repeat_data': repeat_data,
            'show_target': show_target,
            'undo_data': undo_data,
            'timestamp': QDateTime.currentDateTime()
        }
        self._events.append(event)

        # Ограничиваем количество записей
        if len(self._events) > self.MAX_EVENTS:
            self._events = self._events[-self.MAX_EVENTS:]

        self._save()
        self.event_added.emit(event)

    def all_events(self):
        return self._events.copy()