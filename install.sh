#!/bin/bash
set -e

echo "============================================"
echo "   VoiceBot — установка на Ubuntu"
echo "============================================"

# ─── 1. Системные зависимости ──────────────────
echo ""
echo "[1/6] Устанавливаем системные пакеты..."
apt-get update -q
apt-get install -y -q python3 python3-pip python3-venv ffmpeg git

# ─── 2. Виртуальное окружение ──────────────────
echo ""
echo "[2/6] Создаём виртуальное окружение..."
python3 -m venv venv
source venv/bin/activate

# ─── 3. Python-зависимости ─────────────────────
echo ""
echo "[3/6] Устанавливаем Python-зависимости..."
pip install --upgrade pip -q
pip install -r requirements.txt

# ─── 4. Загрузка модели Whisper ────────────────
echo ""
echo "[4/6] Загружаем модель Whisper (medium)..."
echo "Это может занять несколько минут при первом запуске..."
python3 -c "
from faster_whisper import WhisperModel
print('Downloading Whisper medium model...')
WhisperModel('medium', device='cpu', compute_type='int8')
print('Model ready.')
"

# ─── 5. Настройка .env ─────────────────────────
echo ""
echo "[5/6] Настройка конфигурации..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  Файл .env создан из .env.example"
    echo "    Заполни его перед запуском:"
    echo "    nano .env"
else
    echo "    .env уже существует, пропускаем."
fi

# ─── 6. Systemd сервис ─────────────────────────
echo ""
echo "[6/6] Создаём systemd-сервис..."

BOT_DIR=$(pwd)

cat > /etc/systemd/system/voicebot.service << EOF
[Unit]
Description=Telegram VoiceBot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${BOT_DIR}
ExecStart=${BOT_DIR}/venv/bin/python3 main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable voicebot

echo ""
echo "============================================"
echo "   ✅ Установка завершена!"
echo "============================================"
echo ""
echo "Следующие шаги:"
echo ""
echo "  1. Заполни конфиг:"
echo "     nano .env"
echo ""
echo "  2. Запусти бота:"
echo "     systemctl start voicebot"
echo ""
echo "  3. Проверь логи:"
echo "     journalctl -u voicebot -f"
echo ""
echo "  Управление сервисом:"
echo "     systemctl stop voicebot    — остановить"
echo "     systemctl restart voicebot — перезапустить"
echo "     systemctl status voicebot  — статус"
echo ""
