#!/vault-swift/jingyz/.local/bin/zsh

export SPLIT=1

opertaion='remove'

collection='site_replay'
file_prefix='replay-static-1-other'
ts='202503161726'

cd "$(dirname "$0:A")/.."
python3 ts_ops.py --op=$opertaion --collection=$collection --file_prefix=$file_prefix --ts=$ts