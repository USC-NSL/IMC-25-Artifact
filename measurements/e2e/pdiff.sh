#!/vault-swift/jingyz/.local/bin/zsh

TIMEOUT=$((60*60*1)) # 1 hour

# stage='missing_scripts'
groundTruth='replay-202501260006'
static='replay-static-202501200202-202501260006'
patch='replay-static-fuzzy-202501200202-202501260006'
# tag='fuzzy-5w'

# operation='missing'
# operation='diff'
# operation='plot'
operation='merge'

export PREFIX='static_replay'
export SPLIT=1


cd "$(dirname "$0:A")/.."
if [[ "$operation" == "plot" ]]; then
    source /vault-swift/jingyz/pyenv/plotly/bin/activate
fi
python3 patch_diff.py --ground_truth $groundTruth --static=$static --patch=$patch --tag=$tag $operation 2>&1 | tee logs/pdiff_$HOST.log