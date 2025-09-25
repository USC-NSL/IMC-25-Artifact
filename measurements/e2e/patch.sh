#!/vault-swift/jingyz/.local/bin/zsh

export PREFIX='static_replay'
export SPLIT=1
export SEPARATE_COLLECTION='replay_patch'

dynamicTS='202501200202'
staticTS='202501260006'
collection='static_replay'

cd "$(dirname "$0:A")/.."
python3 patch_upload.py --dynamic_ts=${dynamicTS} --static_ts=${staticTS} --collection=$collection
