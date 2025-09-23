# Code for running record and replay on the browser with webrecorder and pywb
## Requirements
- ```pywb``` installed and run (assumed on port 8080, but can be changed)
- ```puppeteer``` installed, with the controled browser installed webrecorder extension

## Workflow
- Record the page with webrecorder (```record.js```)
- Download the warc file from webrecorder, and import it into pywb (```autorecord.py```)
- Replay the page with pywb (```replay.py```)


## Record phase
1. Open webrecorder extension page on Chrome and start recording.
    - Choose an archive(**need to be already created!**)
    - Create a new recording by clicking the recording button.
2. Load a dummy page (```localhost:8086```). 
    - The reason to load the dummy page is to prepare the recording environment before loading the actual page (step 3).
3. Load the actual page.
4. Wait for the page to be loaded. Two ways to do this:
    - Automatically: wait for the event of ```networkIdle``` (or 30s max)
    - Manually: Controlled by the user. Specified with ```--manual, -m``` flag.
5. (Optional) Trigger interaction
    - Not fully tested. Run with ````--interaction, -i``` flag.
6. (Optional) Collect execution and request info.
7. (Optional) Collect the screenshots and all other measurement for checking fidelity
    - Currently, the measurement will collect the self-built layout tree, and the failed network fetches and exceptions (```exceptionFF```)
8. Download the recorded warc file
9. (Optional) Remove the recording from webrecorder
    - If the crawl is large, we need to remove given the limit space of VM.


## Replay phase
1. Load the page.
2. (Optional) If replaying on Wayback, need to remove the banner for fidelity consistency
3. Wait for the page to be loaded.
4. (Optional) Trigger interaction
5. (Optional) Collect execution and request info.
6. (Optional) Collect the screenshots and all other measurement for checking fidelity
