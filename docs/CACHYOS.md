# Codex Desktop для CachyOS / Arch Linux

Эта сборка использует community-проект
[ilysenko/codex-desktop-linux](https://github.com/ilysenko/codex-desktop-linux).
Он упаковывает официальный Linux payload OpenAI в пакет pacman. Это
неофициальная дистрибуция: в меню она называется **ChatGPT Community**,
команда — `codex-desktop`, каталог установки — `/opt/codex-desktop`.
Интерфейс и встроенный Codex берутся из upstream; отдельный терминальный
клиент не заменяет desktop-приложение.

## Сборка и установка на CachyOS

Сначала установи зависимости штатным pacman. Команда обновляет систему целиком,
как требуется для rolling-release Arch; частичный `pacman -Sy` не используется.

```bash
sudo pacman -Syu --needed base-devel ca-certificates curl dpkg git gnupg nodejs npm python tar unzip util-linux xz zstd
```

Из корня **этого** checkout:

```bash
bash scripts/build-cachyos.sh --check
bash scripts/build-cachyos.sh
sudo pacman -U dist/codex-desktop-latest.pkg.tar.zst
codex-desktop
```

Скрипт собирает `.pkg.tar.zst` от обычного пользователя. Он не устанавливает
пакет, не добавляет APT-репозиторий и не запускает скрипты официального `.deb`.
Загрузка идёт с `persistent.oaistatic.com`: сначала проверяется подписанный
`InRelease` закреплённым ключом, затем SHA-256 индекса и самого пакета.
Сборка прекращается при ошибке подписи, контрольной суммы или загрузки.

Нужен Node.js 22.12+ для инструмента ASAR; актуальный пакет `nodejs` в Arch
подходит. По умолчанию выбран базовый интерфейс без дополнительных community-функций
и автоматического updater. Rust для этой сборки не требуется. Локальный
`linux-features/features.json` не перезаписывается. Для обновления повтори сборку
и `pacman -U`; данные аккаунта и проектов не удаляются. Более гибкая сборка
с функциями/updater доступна через обычные команды upstream в README.

Поддерживаются upstream-архитектуры x86_64 и aarch64. CachyOS явно распознаётся
как pacman-дистрибутив даже без `ID_LIKE=arch` в `/etc/os-release`.
Стандартные зависимости графического runtime устанавливает pacman из пакета.

## KDE / Wayland

Launcher upstream выбирает графический backend по сеансу. Если на конкретном
драйвере окно не отображается, сначала посмотри диагностику:

```bash
codex-desktop --diagnose
CODEX_OZONE_PLATFORM=x11 codex-desktop
```

Второй вариант требует XWayland. Не отключай Electron sandbox для обычного
запуска. Для диагностики native Wayland можно использовать
`CODEX_OZONE_PLATFORM=wayland codex-desktop`. Эти варианты требуют проверки
на твоём реальном графическом сеансе.

## Границы проверки в облаке

Среда сборки — Debian, а не CachyOS. Здесь прошёл 61 тест распознавания
дистрибутива, проверки подписанного источника, совместимости и упаковки.
Upstream `chatgpt_26.1007.21434_amd64.deb` получен из подписанного stable-индекса;
его SHA-256 — `276b5341c3d74b261d3ad52106f7fa7edde06841e4767fe2a40cb54099b1f3ed`.
Собран `codex-desktop-26.1007.21434-1-x86_64.pkg.tar.zst` стандартным makepkg.
Контрольные суммы исходного runtime и встроенных инструментов проверяются
при проверке готового пакета. Применён один обязательный upstream community
patch `quit-confirmation-focus`; дополнительных функций не включено.

Встроенные Codex и ripgrep запускаются. Авторизация, работа с проектом и
финальный графический запуск KDE/Wayland требуют проверки на CachyOS:
облачный контейнер запрещает создание user namespaces для sandbox. Sandbox
при сборке и запуске не отключается. В меню пакет отображается как
**ChatGPT Community**; это название upstream community-проекта.

Исходный архив `.deb` был проверен по подписанному индексу и затем повторно
использован как локальный файл, чтобы избежать повторных загрузок. Поэтому
`build-info.json` содержит `repository: null`; доказательства подписанного
происхождения сохраняются отдельно в отчёте проверки.
