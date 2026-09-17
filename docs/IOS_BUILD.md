# Сборка TaskTimer IPA (iOS)

> **Важно:** IPA **нельзя** собрать на Windows или Linux. Нужен **macOS + Xcode**.
> Эта Linux-машина готовит код и `pyproject.toml`; финальный `flet build ipa` — только на Mac.

## Bundle ID

- **Bundle ID:** `com.rom4ik121.tasktimer`
- **Org:** `com.rom4ik121`
- **Product:** TaskTimer

В [Apple Developer → Identifiers](https://developer.apple.com/account/resources/identifiers/list) создайте App ID с **точным** Bundle ID `com.rom4ik121.tasktimer`.

## Требования (Mac)

1. **macOS** (Apple Silicon: при необходимости Rosetta 2)
2. **Xcode 15+** — откройте один раз, примите лицензию, установите компоненты
3. **CocoaPods** ≥ 1.16 (`sudo gem install cocoapods` или через Homebrew)
4. **Python 3.11–3.13** + `pip install -e .` / зависимости из `pyproject.toml`
5. **Apple Developer Program** (платная подписка) — для установки на устройство и TestFlight/App Store
6. **Signing:** сертификат (Apple Development / Distribution) + Provisioning Profile под Bundle ID

## Зависимости и iOS wheels

В `pyproject.toml` зафиксирован **`SQLAlchemy==2.0.36`** — у этой версии есть колёса под iOS в фиде Flet. Более новые SQLAlchemy без iOS wheel ломают `flet build ipa`.

**flet-charts:** Python-пакет `py3-none-any` (расширение Flutter). Если на iOS расширение не подтянется, UI аналитики/колец использует fallback без графиков (см. код). Риск: на симуляторе/устройстве проверьте экран «Статы».

## Команды

Из корня репозитория на Mac:

```bash
# зависимости
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install "flet>=0.86" "SQLAlchemy==2.0.36" "pydantic>=2" "flet-charts>=0.86"

# симулятор (без подписи / Team ID)
flet build ios-simulator

# IPA для отладки на своём устройстве
flet build ipa --ios-team-id YOUR_10_CHAR_TEAM_ID --ios-export-method debugging
```

Параметры подписи также можно прописать в `pyproject.toml` → `[tool.flet.ios]` (`team_id`, `provisioning_profile`, `signing_certificate`). CLI-флаги имеют приоритет.

Другие `export_method`: `debugging` | `release-testing` | `app-store-connect` | `enterprise`.

## Подпись (кратко)

1. Создайте **App ID** = `com.rom4ik121.tasktimer`
2. Выпустите сертификат **Apple Development** (или Distribution для магазина) и установите `.cer` в Keychain
3. Создайте **Provisioning Profile** (Development / Ad Hoc / App Store) на этот App ID + ваши устройства
4. Установите профиль (Xcode или `~/Library/MobileDevice/Provisioning Profiles/`)
5. Соберите: `flet build ipa --ios-team-id … --ios-export-method debugging`
6. Установка на iPhone: Apple Configurator / Xcode Devices, либо TestFlight после `app-store-connect`

Если сборка даёт только `.xcarchive` без `.ipa` — не хватает профиля/сертификата (неподписанный архив).

## Face ID

В Info.plist уже есть `NSFaceIDUsageDescription` (RU) через `[tool.flet.ios.info]`.

Разблокировка по Face ID в Flet 0.86 **ещё без плагина local_auth**: основной путь — **PIN**. Переключатель Face ID в настройках сохраняет предпочтение; на iOS UI не врёт, что desktop Face ID работает.

## Иконка и splash

- `assets/icon.png` — общий источник
- `assets/icon_ios.png` — ≥1024×1024, непрозрачный фон `#0F0F12`
- Splash: `#0F0F12` (charcoal)

## Чего нет на этой Linux-коробке

Здесь **нет** Xcode → реальный IPA / `.app` симулятора **не производится**. Артефакты после Mac: `build/ipa/*.ipa` или `build/ios-simulator/`.
