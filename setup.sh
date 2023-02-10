SERVICE_FILE=./bot.service
BASHRC_FILE=/home/$USER/.bashrc
BASHRC_LINE="export XDG_RUNTIME_DIR=/run/user/$(id -u)"

if [ $(echo $USER) = "root" ]; then
    echo "Running this script as root is not recommended, please create" \
    "a dedicated user with \"adduser username\", add it to the sudo group with" \
    "\"usermod -aG sudo username\" and remove it from the group with \"deluser username sudo\"" \
    "after running both setup scripts"
    exit 0
fi

if [ ! -f "$SERVICE_FILE" ]; then
    echo "bot.service file does not exist, please create it with \"touch bot.service\" and then" \
    "configure it with an editor like nano or vim"
    exit 0
fi

sudo apt update -y
sudo apt upgrade -y
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install -y python3.11

python3.11 -m pip install -r requirements.txt
python3.11 -m playwright install chromium
python3.11 -m playwright install-deps

mkdir -p ~/.config/systemd/user
sudo mv bot.service ~/.config/systemd/user/bot.service

wget -qO- 'http://keyserver.ubuntu.com/pks/lookup?op=get&search=0x6888550b2fc77d09' | sudo tee /etc/apt/trusted.gpg.d/songrec.asc
sudo apt-add-repository ppa:marin-m/songrec -y -u
sudo apt install songrec -y

echo "Script is done running, if you have run the web's setup.sh script already, please remove" \
"sudo privileges from the user running the bot"
echo "Note: If you get \"Failed to connect to bus: Permission denied\" when trying to run systemctl --user," \
"try appending \"$BASHRC_LINE\" to your \"$BASHRC_FILE\" file"