#!/vault-swift/jingyz/.local/bin/zsh

export PREFIX='static_replay'
export SPLIT=1
export SEPARATE_COLLECTION='replay_static'

dynamicTS='202501200202'
staticTS='202503230005'
collection='static_replay'

cd "$(dirname "$0:A")/.."
python3 fetch_inferrable.py --left=replay-${staticTS} --right=replay-static-${dynamicTS}-${staticTS}
