#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic-plugins.plugin.py

    Written by:               Josh.5 <jsunnex@gmail.com>
    Date:                     27 Feb 2022, (12:22 PM)

    Copyright:
        Copyright (C) 2021 Josh Sunnex

        This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
        Public License as published by the Free Software Foundation, version 3.

        This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
        implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
        for more details.

        You should have received a copy of the GNU General Public License along with this program.
        If not, see <https://www.gnu.org/licenses/>.

"""
import logging
import os
import pprint
import time
import pathlib

import humanfriendly
from pyarr import SonarrAPI
from pyarr.exceptions import (
    PyarrAccessRestricted,
    PyarrBadGateway,
    PyarrConnectionError,
    PyarrResourceNotFound,
    PyarrUnauthorizedError,
)
from unmanic.libs.unplugins.settings import PluginSettings

# Configure plugin logger
logger = logging.getLogger("Unmanic.Plugin.notify_sonarr")


class Settings(PluginSettings):
    settings = {
        'host_url':                  'http://localhost:8989',
        'api_key':                   '',
        'mode':                      'update_mode',
        'rename_files':              False,
        'limit_import_on_file_size': True,
        'minimum_file_size':         '100MB',
        'import_root':               '',
        'delay_import':              False,
        'intermediate_root':         '',
        'sources_removed':           False,
    }

    def __init__(self, *args, **kwargs):
        super(Settings, self).__init__(*args, **kwargs)
        self.form_settings = {
            "host_url":                  {
                "label": "Sonarr LAN IP Address",
            },
            "api_key":                   {
                "label": "Sonarr API Key",
            },
            "mode":                      {
                "label":          "Mode",
                "input_type":     "select",
                "select_options": [
                    {
                        'value': "update_mode",
                        'label': "Trigger series refresh on task complete",
                    },
                    {
                        'value': "import_mode",
                        'label': "Import episode on task complete",
                    },
                ],
            },
            "rename_files":              self.__set_rename_files(),
            "limit_import_on_file_size": self.__set_limit_import_on_file_size(),
            "minimum_file_size":         self.__set_minimum_file_size(),
            "import_root":               self.__set_import_root(),
            "delay_import":              self.__set_delay_import(),
            "intermediate_root":         self.__set_intermediate_root(),
            "sources_removed":           self.__set_sources_removed(),
        }
    def __set_rename_files(self):
        values = {
            "label": "Trigger Sonarr file renaming",
        }
        if self.get_setting('mode') != 'update_mode':
            values["display"] = 'hidden'
        return values

    def __set_limit_import_on_file_size(self):
        values = {
            "label": "Limit file import size",
        }
        if self.get_setting('mode') != 'import_mode':
            values["display"] = 'hidden'
        return values

    def __set_minimum_file_size(self):
        values = {
            "label": "Minimum file size",
        }
        if self.get_setting('mode') != 'import_mode':
            values["display"] = 'hidden'
        if not self.get_setting('limit_import_on_file_size'):
            values["display"] = 'hidden'
        return values

    def __set_import_root(self):
        values = {
            "label":       "Import Directory",
            "input_type":  "browse_directory",
            "description": "Specify the root import directory",
            "sub_setting": True,
        }
        if self.get_setting('mode') != 'import_mode':
            values["display"] = 'hidden'
            self.set_setting('import_root', '')
        return values

    def __set_delay_import(self):
        values = {
            "label":       "Delay import until all files are processed",
            "description": "If files are delivered to the import directory by mover this delays import until all files are delivered",
            "sub_setting": True,
        }
        if self.get_setting('mode') != 'import_mode':
            values["display"] = 'hidden'
        if not self.get_setting('import_root'):
            self.set_setting('delay_import', False)
        return values

    def __set_intermediate_root(self):
        values = {
            "label":       "Intermediate Directory",
            "input_type":  "browse_directory",
            "description": "Directory from which mover delivers files",
            "sub_setting": True,
        }
        if self.get_setting('mode') != 'import_mode':
            values["display"] = 'hidden'
        if not self.get_setting('delay_import'):
            self.set_setting('intermediate_root', '')

        return values

    def __set_sources_removed(self):
        values = {
            "label":       "Mover is configured to remove source files",
            "sub_setting": True,
        }
        if self.get_setting('mode') != 'import_mode':
            values["display"] = 'hidden'
        if not self.get_setting('intermediate_root'):
            self.set_setting('sources_removed', False)
        return values


def ordinalize(number):
    ones = number % 10
    if number > 3 and number < 21:
        suffix = 'th'
    elif ones == 1:
        suffix = 'st'
    elif ones == 2:
        suffix = 'nd'
    elif ones == 3:
        suffix = 'rd'
    else:
        suffix = 'th'
    return '%d%s' % (number, suffix)

def check_file_size_under_max_file_size(path, minimum_file_size):
    file_stats = os.stat(os.path.join(path))
    if int(humanfriendly.parse_size(minimum_file_size)) < int(file_stats.st_size):
        return False
    return True


def update_mode(api, dest_path, rename_files):
    basename = os.path.basename(dest_path)

    # Fetch episode data
    episode_data = api.get_parsed_title(basename)

    # Fetch a series ID from Sonarr
    series_title = episode_data.get('series', {}).get('title')
    series_id = episode_data.get('series', {}).get('id')
    if not series_id:
        logger.error("Missing series ID. Failed to queued refresh of series for file: '%s'", dest_path)
        return

    try:
        # Run API command for RescanSeries
        #   - RescanSeries with a series ID
        result = api.post_command('RescanSeries', seriesId=series_id)
        if result.get('message'):
            logger.error("Failed to queue refresh of series ID '%s' for file: '%s'", series_id, dest_path)
            logger.error("Response from sonarr: %s", result['message'])
            return
        else:
            logger.info("Successfully queued refresh of the Series '%s' for file: '%s'", series_id, dest_path)
    except PyarrUnauthorizedError:
        logger.error("Failed to queue refresh of series ID '%s' for file: '%s'", series_id, dest_path)
        logger.error("Unauthorized. Please ensure valid API Key is used.")
        return
    except PyarrAccessRestricted:
        logger.error("Failed to queue refresh of series ID '%s' for file: '%s'", series_id, dest_path)
        logger.error("Access restricted. Please ensure API Key has correct permissions")
        return
    except PyarrResourceNotFound:
        logger.error("Failed to queue refresh of series ID '%s' for file: '%s'", series_id, dest_path)
        logger.error("Resource not found")
        return
    except PyarrBadGateway:
        logger.error("Failed to queue refresh of series ID '%s' for file: '%s'", series_id, dest_path)
        logger.error("Bad Gateway. Check your server is accessible")
        return
    except PyarrConnectionError:
        logger.error("Failed to queued refresh of series ID '%s' for file: '%s'", series_id, dest_path)
        logger.error("Timeout connecting to sonarr. Check your server is accessible")
        return

    if rename_files:
        time.sleep(10) # Must give time (more than Radarr) for the refresh to complete before we run the rename.
        try:
            rename_list = api.get_episode_file(series_id, series=True)
            file_ids = [episode['id'] for episode in rename_list]

            result = api.post_command('RenameFiles', seriesId=series_id, files=file_ids)
            if isinstance(result, dict):
                logger.info("Successfully triggered rename of series '%s' for file: '%s'", series_title, dest_path)
            else:
                logger.error("Failed to trigger rename of series ID '%s' for file: '%s'", series_id, dest_path)
        except PyarrUnauthorizedError:
            logger.error("Failed to trigger rename of series '%s' for file: '%s'", series_title, dest_path)
            logger.error("Unauthorized. Please ensure valid API Key is used.")
        except PyarrAccessRestricted:
            logger.error("Failed to trigger rename of series '%s' for file: '%s'", series_title, dest_path)
            logger.error("Access restricted. Please ensure API Key has correct permissions")
        except PyarrResourceNotFound:
            logger.error("Failed to trigger rename of series '%s' for file: '%s'", series_title, dest_path)
            logger.error("Resource not found")
        except PyarrBadGateway:
            logger.error("Failed to trigger rename of series '%s' for file: '%s'", series_title, dest_path)
            logger.error("Bad Gateway. Check your server is accessible")
        except PyarrConnectionError:
            logger.error("Failed to trigger rename of series '%s' for file: '%s'", series_title, dest_path)
            logger.error("Timeout connecting to sonarr. Check your server is accessible")
        except BaseException as err:
            logger.error("Failed to trigger rename of series ID '%s' for file: '%s'\nError received: %s", series_id, dest_path, str(err))


def import_mode(api, source_path, dest_path, intermediate_root, import_root, sources_removed):
    # identify file/directory to be imported and
    # reconstruct source and dest paths from _root parameters
    
    # we want the first directory (or file) under the source/destination root
    source_basename = os.path.relpath(source_path, intermediate_root).split(os.sep)[0]
    dest_basename = os.path.relpath(dest_path, import_root).split(os.sep)[0]
    
    abspath_source = os.path.join(intermediate_root, source_basename)
    abspath_dest   = os.path.join(import_root, dest_basename)
    abspath_dest   = abspath_dest.replace('\\', '')

    # verify we've reconstructed paths correctly
    if abspath_source not in source_path:
        logger.error("Source file '%s' is not under intermediate root '%s' - file will not be processed.", source_path, intermediate_root)
        return
    if abspath_dest not in dest_path:
        logger.error("Destination file '%s' is not under import root '%s' - file will not be processed.", dest_path, import_root)
        return

    is_dir = os.path.isdir(abspath_source)
    logger.info("%s-type import - processing: '%s'", 'DIR' if is_dir else 'File', dest_path)

    logger.debug("Source:       '%s'", abspath_source)
    logger.debug("Destination:  '%s'", abspath_dest)

    # if delay_processing's enabled (different import and intermediate dirs)
    # don't alert until all files (ignoring dot files) are processed. 
    if is_dir and intermediate_root != import_root:
        sourcefile_count = len(list(pathlib.Path(abspath_source).rglob('[!.]*.*')))
        destfile_count = len(list(pathlib.Path(abspath_dest).rglob('[!.]*.*')))

        logger.debug("Files in import directory:        %d", destfile_count)
        logger.debug("Files in intermediate directory:  %d", sourcefile_count)

        # In the case where mover *doesn't* delete source files:
        #   processing's complete when the number of files are equal.
        # In the casse where it does:
        #   it's complete when the number in source is 0.
        if sources_removed:
            files_remaining = sourcefile_count
        else:
            files_remaining = sourcefile_count - destfile_count
        logger.info("Processing (%d of %d) files", destfile_count, destfile_count + files_remaining)

        if files_remaining > 0:
            # hide the file from sonarr to prevent early import
            newname = dest_path + '.tmp'
            logger.debug("Hiding file as '%s'", newname)
            # in case another notifier hid it (same library might notify sonarr AND radarr)
            if not os.path.exists(newname):
                os.rename(dest_path, newname)
            return
        else:
            logger.info("All files processed, notifying sonarr")
            # unhide all hidden files
            for tmp_file in list(pathlib.Path(abspath_dest).rglob('*.tmp')):
                logger.debug("Un-hiding file '%s'", os.path.splitext(tmp_file)[0])
                os.rename(tmp_file, os.path.splitext(tmp_file)[0])
            os.chmod(abspath_dest, 0o777)
        
    download_id = None
    episode_title = None

    queue = api.get_queue()
    message = pprint.pformat(queue, indent=1)

    logger.debug("Current queue \n%s", message)
    logger.debug("Searching queue for: '%s'", dest_basename)
    match = False

    for item in queue.get('records', []):
        # we should have an outputPath if everything goes well but sometimes it doesn't
        if not item.get('outputPath'):
            continue
        item_output_basename = os.path.basename(item.get('outputPath'))
        logger.debug("    - candidate: '%s'", item_output_basename)

        if is_dir:
            if dest_basename == item_output_basename:
                match = True
        else:
            # if dest is a file ignore extension, to handle remux
            if os.path.splitext(dest_basename)[0] == os.path.splitext(item_output_basename)[0]:
                match = True
        if match:
            logger.debug("        * match *")
            download_id = item.get('downloadId')
            episode_title = item.get('title')
            break

    ## Seems sonarr will automatically match and import files
    #  if there's a subdirectory match even if the extensions differ.
    #  Triggering it typically results in a double-import, so let's not.
    if download_id and is_dir:
        logger.info("Supressing import trigger to avoid double-import; file is in a named directory which sonarr imports automatically")
        return
        
    # Run import
    if download_id:
        # Run API command for DownloadedEpisodesScan
        #   - DownloadedEpisodesScan with a path and downloadClientId
        logger.info("Queued import episode '%s' using downloadClientId: '%s'", episode_title, download_id)
        result = api.post_command('DownloadedEpisodesScan', path=abspath_dest, downloadClientId=download_id)
    else:
        # Run API command for DownloadedEpisodesScan without passing a downloadClientId
        #   - DownloadedEpisodesScan with a path and downloadClientId
        logger.info("Queued import using just the file path '%s'", abspath_dest)
        result = api.post_command('DownloadedEpisodesScan', path=abspath_dest)

    # Log results
    message = result
    if isinstance(result, dict) or isinstance(result, list):
        message = pprint.pformat(result, indent=1)
    logger.debug("Queued import result \n%s", message)
    if (isinstance(result, dict)) and result.get('message'):
        logger.error("Failed to queued import of: '%s'", abspath_dest)
        return
    # TODO: Check for other possible outputs
    logger.info("Successfully queued import of: '%s'", abspath_dest)


def process_files(settings, source_file, destination_files, host_url, api_key):
    api = SonarrAPI(host_url, api_key)

    mode = settings.get_setting('mode')
    rename_files = settings.get_setting('rename_files')
    import_root = settings.get_setting('import_root')
    if settings.get_setting('delay_import') and settings.get_setting('intermediate_root'):
        intermediate_root = settings.get_setting('intermediate_root')
    else:
        intermediate_root = import_root
    sources_removed = settings.get_setting('sources_removed')
    
    for dest_file in destination_files:
        if mode == 'update_mode':
            update_mode(api, dest_file, rename_files)
        elif mode == 'import_mode':
            minimum_file_size = settings.get_setting('minimum_file_size')
            # ignore file-size with delayed imports
            if not settings.get_setting('delay_import') and check_file_size_under_max_file_size(dest_file, minimum_file_size):
                # Ignore this file
                logger.info("Ignoring file as it is under configured minimum size file: '%s'", dest_file)
                continue
            logger.debug("Calling import source with source_file: '%s', dest_file: '%s'", source_file, dest_file)
            import_mode(api, source_file, dest_file, intermediate_root, import_root, sources_removed)


def on_postprocessor_task_results(data):
    """
    Runner function - provides a means for additional postprocessor functions based on the task success.

    The 'data' object argument includes:
        library_id                      - The library that the current task is associated with
        task_processing_success         - Boolean, did all task processes complete successfully.
        file_move_processes_success     - Boolean, did all postprocessor movement tasks complete successfully.
        destination_files               - List containing all file paths created by postprocessor file movements.
        source_data                     - Dictionary containing data pertaining to the original source file.

    :param data:
    :return:

    """
    # Configure settings object (maintain compatibility with v1 plugins)
    if data.get('library_id'):
        settings = Settings(library_id=data.get('library_id'))
    else:
        settings = Settings()

    # Fetch destination and source files
    source_file = data.get('source_data', {}).get('abspath')
    destination_files = data.get('destination_files', [])

    # Setup API
    host_url = settings.get_setting('host_url')
    api_key = settings.get_setting('api_key')
    process_files(settings, source_file, destination_files, host_url, api_key)
