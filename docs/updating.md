# Updating CineMate While Keeping Your Custom `settings.json`

| :exclamation:  Note that if you update this repo, your settings file will be overwritten with the latest default CineMate settings file. If you are using a custom settings file, be sure to copy it to somewhere outside of the CineMate folder before updating, or see below for how to exclude the file from the git update.   |
|-----------------------------------------|

To ensure that you can update the CineMate repository on your Raspberry Pi while retaining your custom settings in `/src/settings.json`, follow these steps:

1. Navigate to the CineMate directory and stop any autostarted instance of CineMate.

    ```shell
    cd cinemate
    make stop
    ```

2. Stash Your Custom Settings File

    Before updating, stash your `settings.json` file to prevent it from being overwritten during the update:

    ```shell
    git stash push src/settings.json -m "Saving custom settings.json"
    ```

3. Pull the Latest Updates

    Pull the latest updates from the development branch of the CineMate repository:

    ```shell
    git pull origin development
    ```

4. Reapply Your Custom Settings

    After pulling the updates, reapply your `settings.json` file:

    ```shell
    git stash pop
    ```

    If you encounter any merge conflicts with `settings.json`, Git will notify you. Resolve the conflicts by manually merging the changes, and then commit the resolved version of `settings.json`.

5. Restart CineMate

    ```shell
    cinemate
    ```

# Note on Future Updates

It's a good practice to keep a backup of your `settings.json` file outside the repository directory. This ensures that you have a copy of your custom settings in case of unexpected changes or merge conflicts.
