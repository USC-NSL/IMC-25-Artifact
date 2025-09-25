## Run patch
- ```./patch.sh```

- ```./remove.sh```

- ```./replay.sh```
  - stage='replay_patch'
  - specify ```dynamicTS``` and ```ts```
  - PREFIX

- ```./diff.sh```

## Run diff
- ```./diff.sh```
  - left should be ground truth data (like native replay)
  - right should be the one to compare (like static, patch or cache). With two ts included

## Run record
- ```cd cronjobs && python3 weekly_record.py```

## Run native replay
- ```./extract.sh```
  - Comment out other TS variable other than ```dynamicTS```
  - Specify ```dynamicTS```
  - If separate collection
    - ```export SEPARATE_COLLECTION='replay'```
- ```./replay.sh```
  - stage='replay'
  - Change ```ts``` to ```dynamicTS``` in extract.sh
  - If separate collection
    - ```export SEPARATE_COLLECTION='replay'```


## Run replay-static (with dynamic cache extraction)
- ```./extract.sh```
  - Specify ```dynamicTS```
    - If want to specify multiple dynamic files, split by comma (`,`)
  - Specify ```staticTS``` 
    - If cache extraction, also specify ```cacheStaticTS``` (Usually should be the same)
    - If resource match type, also speify ```resourceMatchType```
  - If separate collection
    - ```export SEPARATE_COLLECTION='replay_static'```
- ```./remove.sh```
  - Change ```file_prefix``` to ```replay-static-{dynamicTS}``` / ```replay-static-cache-{dynamicTS}```
  - Change ```ts``` to ```{staticTs}``` / ```{resourceMatchType}-{staticTs}```
- ```./replay.sh```
  - stage='replay_static'
  - Change ```ts``` to ```staticTS``` in extract.sh
  - Change ```dynamicTS``` to ```dynamicTS``` in extract.sh
    - If cache extraction, specify as ```cache=0```
    - If using resource match type, ensure to specify ```resourceMatchType```(same as in extract.sh)
  - If separate collection
    - ```export SEPARATE_COLLECTION='replay_static'```
  