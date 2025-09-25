#!/vault-swift/jingyz/.local/bin/zsh

TIMEOUT=$((20*60*1)) # 1 hour

# stage='missing_scripts'
left='replay-202502020008'
right='replay-static-202501200202-202502020008'

export PREFIX='static_replay'
export SPLIT=1


cd "$(dirname "$0:A")/.."
# python3 layout_diff.py --left $left --right $right missing_scripts 2>&1 | tee logs/layout_diff_$HOST.log
# timeout -k 5s ${TIMEOUT}s python3 layout_diff.py --left $left --right $right fidelity 2>&1 | tee -a logs/layout_diff_$HOST.log
# python3 layout_diff.py --left $left --right $right merge

python3 layout_diff.py --left $left --right $right ground_truth