"""Шифрование секретов в БД (Fernet)."""

from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_PLAIN = "plain:"  # префикс незашифрованного значения (dev без ключа)
_ENC = "enc:"  # префикс зашифрованного значения


class SecBox:
    """Обёртка над Fernet для шифрования секретов в БД.

    В рантайме ключ всегда разрешается резолвером секретов (файл/менеджер), и
    шифрование обязательно. Режим без ключа допускается только для чтения
    легаси-значений — :meth:`seal` без ключа запрещён.
    """

    def __init__(self, key: str | None) -> None:
        self._f: Fernet | None = Fernet(key) if key else None

    @staticmethod
    def new_key() -> str:
        """Сгенерировать новый ключ Fernet (urlsafe base64)."""
        return Fernet.generate_key().decode()

    @staticmethod
    def load_or_create(path: str | Path) -> str:
        """Прочитать ключ из файла, создав его при отсутствии.

        Используется, когда ``SECRETS_KEY_PATH`` не задан в окружении: ключ
        генерируется один раз и кладётся в монтируемую папку данных, чтобы
        переживать перезапуски контейнера.
        """
        p = Path(path)
        if p.exists():
            key = p.read_text(encoding="utf-8").strip()
            if key:
                return key
        p.parent.mkdir(parents=True, exist_ok=True)
        key = SecBox.new_key()
        p.write_text(key, encoding="utf-8")
        return key

    def seal(self, raw: str) -> str:
        """Зашифровать значение для записи в БД.

        :arg raw: открытое значение секрета.
        :return: строка ``enc:<ciphertext>``.
        :raises RuntimeError: если ключ шифрования не задан.
        """
        if self._f is None:
            raise RuntimeError("ключ шифрования секретов обязателен (SECRETS_KEY)")
        return _ENC + self._f.encrypt(raw.encode()).decode()

    def open(self, stored: str) -> str:
        """Расшифровать значение из БД."""
        if stored.startswith(_PLAIN):
            return stored[len(_PLAIN) :]
        if stored.startswith(_ENC):
            if self._f is None:
                raise RuntimeError(
                    "SECRETS_KEY_PATH не задан, секрет нельзя расшифровать"
                )
            try:
                return self._f.decrypt(stored[len(_ENC) :].encode()).decode()
            except InvalidToken as exc:
                raise RuntimeError(
                    "Неверный SECRETS_KEY_PATH или повреждённый секрет"
                ) from exc
        # Легаси / сырое значение без префикса.
        return stored


__all__ = ["SecBox"]
