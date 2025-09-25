#!/vault-swift/jingyz/.local/bin/zsh

export SPLIT=1

opertaion='rename'

collection='static_replay'
file_prefix='replay-static-202501200202'
ts='exxhr3-202503230005'
rename_ts='exxhr3-1-202503230005'

cd "$(dirname "$0:A")/.."
python3 ts_ops.py --op=$opertaion --collection=$collection --file_prefix=$file_prefix --ts=$ts --rename_ts=$rename_ts