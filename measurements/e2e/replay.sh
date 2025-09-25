#!/vault-swift/jingyz/.local/bin/zsh

stage='replay'

flags=()
ts='202501200202'
# dynamicTS='1-2-other-202505030245'
# * replay_static
# pywbPatch=1
# cache=1
# resourceMatchType='exclude_all'
#     inferrable=1

export PREFIX='static_replay'
export SEPARATE_COLLECTION='replay'
export SPLIT=1

cd "$(dirname "$0:A")/.."
# Based on stage, run different scripts
if [ $stage = 'replay' ]; then
    python3 auto_replay.py --ts $ts 2>&1 | tee logs/auto_replay_$HOST.log
elif [ $stage = 'replay_static' ]; then
    if [ -n "$cache" ]; then
        flags+=("--cache")
    fi
    if [ -n "$resourceMatchType" ]; then
        flags+=("--resource_match_type=${resourceMatchType}")
        # export PYWB_STRIP_MATCH=$resourceMatchType
    fi
    if [ -n "$inferrable" ]; then
        flags+=("--inferrable")
    fi
    if [ -n "$pywbPatch" ]; then
        export PYWB_PATCH=1
    fi
    python3 auto_replay_static.py --ts $ts --dynamic_ts=$dynamicTS "${flags[@]}" 2>&1 | tee logs/auto_replay_static_$HOST.log
elif [ $stage = 'replay_patch' ]; then
    # export PYWB_PATCH=1
    # * Might need to run ./remove.sh first to remove old patch
    python3 auto_replay_patch.py --ts $ts --dynamic_ts=$dynamicTS 2>&1 | tee logs/auto_replay_patch_$HOST.log
else
    echo "Invalid stage: $stage"
    exit 1
fi