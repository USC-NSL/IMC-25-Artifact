#!/vault-swift/jingyz/.local/bin/zsh

# HOME=/vault-swift/jingyz
# PATH=/vault-swift/jingyz/.nvm/versions/node/v16.20.2/bin:/vault-swift/jingyz/.local/bin:/vault-home/jingyz/.vscode-server/cli/servers/Stable-cd4ee3b1c348a13bafd8f9ad8060705f6d4b9cba/server/bin/remote-cli:/vault-swift/jingyz/anaconda3/bin:/vault-home/jingyz/anaconda3/condabin:/vault-home/jingyz/.local/lib/nodejs/node-v10.16.3-linux-x64/bin:/vault-home/jingyz/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin:/vault-home/jingyz/.local/go/bin:/vault-home/jingyz/.local/bin/azure-cli:/vault-home/jingyz/.vscode-server/data/User/globalStorage/github.copilot-chat/debugCommand:/vault-swift/jingyz/.local/go/bin:/vault-swift/jingyz/deps/dotnet
# PYTHONPATH=$HOME:$PYTHONPATH

# export PREFIX='static_replay'
export SPLIT=1

cd "$(dirname "$0:A")/.."
# source $HOME/pyenv/$HOST/bin/activate
python3 auto_record.py 2>&1 | tee logs/auto_record_$HOST.log