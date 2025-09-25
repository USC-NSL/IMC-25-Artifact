#!/vault-swift/jingyz/.local/bin/zsh

export PREFIX='site_replay'
export SPLIT=1
export SEPARATE_COLLECTION='replay_static'
# If SEPARATE_COLLECTION is set, this specify a single collection that stores extracted & uploaded warcs 
collection='replay_static'

flags=()
dynamicTS='202505030245'
staticTS='202505042131'

# * Dynamic extraction
cacheStaticTS='202505042131'
dynamicOtherURL=1
dynamicPrefix='record'
# selectExtractInfo='metadata/site_replay_extract_info'

#! TEMP Ensure either selectExtractInfo or dynamicOtherURL is defined
if [ -z "$selectExtractInfo" ] && [ -z "$dynamicOtherURL" ]; then
    echo "Error: Either selectExtractInfo or dynamicOtherURL must be defined."
    exit 1
fi


# * Static extraction
bypassStatic=1
bypassReplay=1
staticPrefix='record'
# resourceMatchType='exclude_all'
    # num_throw_resources=1
    # run_id=0

    # inferrable_dir="/vault-swift/jingyz/static_replay_measure/diffs/static_replay/replay-${staticTS}_replay-static-${dynamicTS}-${staticTS}/"


cd "$(dirname "$0:A")/.."
if [ -n "$dynamicTS" ]; then
    flags+=("--dynamic_ts=${dynamicTS}")
fi
if [ -n "$staticTS" ]; then
    flags+=("--static_ts=${staticTS}")
fi
if [ -n "$cacheStaticTS" ]; then
    flags+=("--cache_static_ts=${cacheStaticTS}")
fi
if [ -n "$dynamicOtherURL" ]; then
    flags+=("--dynamic_other_url=${dynamicOtherURL}")
fi
if [ -n "$dynamicPrefix" ]; then
    flags+=("--dynamic_prefix=${dynamicPrefix}")
fi
if [ -n "$bypassStatic" ]; then
    flags+=("--bypass_static")
fi
if [ -n "$bypassReplay" ]; then
    flags+=("--bypass_replay")
fi
if [ -n "$staticPrefix" ]; then
    flags+=("--static_prefix=${staticPrefix}")
fi
if [ -n "$resourceMatchType" ]; then
    flags+=("--resource_match_type=${resourceMatchType}")
fi
if [ -n "$selectExtractInfo" ]; then
    flags+=("--select_extract_info=${selectExtractInfo}")
fi
if [ -n "$num_throw_resources" ]; then
    flags+=("--num_throw_resources=${num_throw_resources}")
fi
if [ -n "$run_id" ]; then
    flags+=("--run_id=${run_id}")
fi
if [ -n "$inferrable_dir" ]; then
    flags+=("--inferrable_dir=${inferrable_dir}")
fi

echo "Running extract_upload.py with flags: ${flags}"
python3 extract_upload.py "${flags[@]}" --collection=$collection