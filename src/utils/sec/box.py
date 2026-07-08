"""Шифрование секретов в БД (Fernet, с поддержкой ротации ключей)."""

from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

_ENC = "enc:"  # префикс зашифрованного значения


def _parse_keys(raw: str) -> list[str]:
    """Разобрать ``SECRETS_KEY`` в упорядоченный список ключей Fernet.

    Поддерживаемые форматы (через запятую):
    - один ключ: ``"<key>"`` (обычный случай, без ротации);
    - список с версионными метками: ``"v2:<key2>,v1:<key1>"`` — метки нужны
      только для читаемости конфигурации оператором, сам порядок в списке и
      определяет приоритет (**первый** элемент — текущий ключ для *записи*,
      остальные — только для чтения старых данных при расшифровке).

    :arg raw: значение ``SECRETS_KEY``/секрета из хранилища.
    :return: список ключей Fernet без версионных меток, в порядке приоритета.
    """
    keys: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            _, _, key = part.rpartition(":")
        else:
            key = part
        keys.append(key)
    return keys


class SecBox:
    """Обёртка над Fernet/MultiFernet для шифрования секретов в БД.

    Шифрование обязательно — режима "без ключа" не существует, ``seal()``
    без ключа запрещён.

    Ротация ключей (IMPLEMENTATION_PLAN §12): ``key`` может быть списком через
    запятую (``"v2:<new>,v1:<old>"``) — шифрование всегда идёт первым
    (новейшим) ключом, расшифровка пробует все по очереди (``MultiFernet``),
    поэтому старые данные остаются читаемыми без немедленного bulk-rewrite.
    Впервые сгенерированный секрет уже создаётся в версионированном формате
    (см. :meth:`new_versioned_key`, используется ``resolve_secrets()``) —
    ротация не требует никакой миграции формата, только добавления нового
    ключа первым в список. Старый ключ можно удалить из списка только когда
    ни одной строки в старом формате не осталось (см. ``utils/sec/rotate.py``).
    """

    def __init__(self, key: str | None) -> None:
        self._f: MultiFernet | None = None
        if key:
            fernets = [Fernet(k) for k in _parse_keys(key)]
            self._f = MultiFernet(fernets) if fernets else None

    @staticmethod
    def new_key() -> str:
        """Сгенерировать новый ключ Fernet (urlsafe base64), без версионной метки."""
        return Fernet.generate_key().decode()

    @staticmethod
    def new_versioned_key(version: str = "v1") -> str:
        """Сгенерировать новый ключ Fernet сразу в версионированном формате.

        Используется при первом создании секрета (``resolve_secrets()``),
        чтобы будущая ротация не требовала миграции формата — достаточно
        добавить новый ключ первым: ``"v2:<new>," + текущее_значение``.
        """
        return f"{version}:{SecBox.new_key()}"

    @staticmethod
    def load_or_create(path: str | Path) -> str:
        """Прочитать ключ из файла, создав его при отсутствии.

        Используется, когда ``SECRETS_KEY_PATH`` не задан в окружении: ключ
        генерируется один раз (сразу в версионированном формате) и кладётся
        в монтируемую папку данных, чтобы переживать перезапуски контейнера.
        """
        p = Path(path)
        if p.exists():
            key = p.read_text(encoding="utf-8").strip()
            if key:
                return key
        p.parent.mkdir(parents=True, exist_ok=True)
        key = SecBox.new_versioned_key()
        p.write_text(key, encoding="utf-8")
        return key

    def seal(self, raw: str) -> str:
        """Зашифровать значение для записи в БД.

        Всегда используется самый новый (первый в списке) ключ — ``MultiFernet``
        шифрует именно им.

        :arg raw: открытое значение секрета.
        :return: строка ``enc:<ciphertext>``.
        :raises RuntimeError: если ключ шифрования не задан.
        """
        if self._f is None:
            raise RuntimeError("ключ шифрования секретов обязателен (SECRETS_KEY)")
        return _ENC + self._f.encrypt(raw.encode()).decode()

    def open(self, stored: str) -> str:
        """Расшифровать значение из БД.

        При нескольких настроенных ключах ``MultiFernet`` пробует их по
        очереди — данные, зашифрованные ещё не отозванным старым ключом,
        расшифровываются прозрачно, без миграции "здесь и сейчас".

        Значения без префикса ``enc:`` возвращаются как есть (используется
        тестовыми фикстурами, которые сидят данные напрямую в БД в обход
        приложения — см. ``tests/integration/conftest.py``); в самом
        приложении такие значения не пишутся — ``seal()`` всегда добавляет
        префикс.
        """
        if not stored.startswith(_ENC):
            return stored
        if self._f is None:
            raise RuntimeError("SECRETS_KEY_PATH не задан, секрет нельзя расшифровать")
        try:
            return self._f.decrypt(stored[len(_ENC) :].encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError(
                "Неверный SECRETS_KEY_PATH или повреждённый секрет"
            ) from exc


__all__ = ["SecBox"]
