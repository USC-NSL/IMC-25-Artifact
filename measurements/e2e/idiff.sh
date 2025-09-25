#!/vault-swift/jingyz/.local/bin/zsh

TIMEOUT=$((60*60*1)) # 1 hour

groundTruth='replay-202503230005'
static='replay-static-202501200202-202503230005'
infer='replay-static-202501200202-inferrable-202503230005'
# tag='fuzzy-5w'

# operation='diff'
operation='merge'

export PREFIX='static_replay'
export SPLIT=1


cd "$(dirname "$0:A")/.."
python3 infer_diff.py --ground_truth $groundTruth --static=$static --infer=$infer  $operation 2>&1 | tee logs/idiff_$HOST.log