# NetGrid Monitor

Uptime monitoring для сайтов netgrid.host через **GitHub Actions** (бесплатно, без использования ресурсов VPS).

## Что мониторит

| Сайт | URL | Проверка |
|------|-----|----------|
| babycloud.by | https://babycloud.by/ | HTTP 200, SSL expiry |
| premiumfuji.by | https://premiumfuji.by/ | HTTP 200, SSL expiry |
| refgroup.by | http://188.255.163.132/ (Host: refgroup.by) | HTTP 200 |

## Интервал

Каждый час (UTC) — настраивается в `.github/workflows/monitor.yml` (`cron: '0 * * * *'`).

## Уведомления

- **Telegram** — при down'е или SSL < 14 дней
- **GitHub Actions status** — красный/зелёный бейдж в README

## Настройка

### 1. Создать репозиторий на GitHub

- Название: `netgrid-monitor`
- Public или Private — без разницы
- **Не инициализировать** README (мы загрузим сами)

### 2. Добавить Secrets

В настройках репозитория → **Settings → Secrets and variables → Actions**:

| Secret | Описание |
|--------|----------|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота (получить у @BotFather) |
| `TELEGRAM_CHAT_ID` | ID чата для уведомлений |

### 3. Загрузить файлы

```bash
git init
git remote add origin https://github.com/ClarenceFerreiro/netgrid-monitor.git
git add .
git commit -m "Initial monitor setup"
git push -u origin main
```

### 4. Запустить вручную

GitHub → Actions → Site Monitor → **Run workflow**.

### 5. Проверить Telegram

При первом запуске (если всё OK) уведомления не придёт. Чтобы протестировать — временно поменяй URL в `monitor.py` на несуществующий, запусти workflow, верни обратно.

## Изменение списка сайтов

Отредактируй `SITES` в `monitor.py`:

```python
SITES = [
    {"name": "example.com", "url": "https://example.com/", "expected": 200},
]
```

## Локальный тест

```bash
python monitor.py
```

## Лицензия

MIT — используй как хочешь.
