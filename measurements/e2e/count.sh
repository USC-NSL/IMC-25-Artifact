#!/vault-swift/jingyz/.local/bin/zsh

export SPLIT=1

opertaion='count'

collection='static_replay'
file_prefix='replay-static-202501200202'
ts='exjs-202503230005'

cd "$(dirname "$0:A")/.."
python3 ts_ops.py --op=$opertaion --collection=$collection --file_prefix=$file_prefix --ts=$ts