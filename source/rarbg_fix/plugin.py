#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging

from unmanic.libs.unplugins.settings import PluginSettings
from rarbg_fix.lib import ffmpeg
from rarbg_fix.lib import mkvtoolnix

# Configure plugin logger
logger = logging.getLogger("Unmanic.Plugin.rarbg_fix")


class Settings(PluginSettings):
    settings = {}

    def __init__(self, *args, **kwargs):
        super(Settings, self).__init__(*args, **kwargs)

        
class PluginStreamMapper(ffmpeg.StreamMapper):
    def __init__(self):
        super(PluginStreamMapper, self).__init__(logger, ['video'])
        self.settings = None

    def set_settings(self, settings):
        self.settings = settings

    def test_stream_needs_processing(self, stream_info: dict):
        """Check if file has an hevc stream """
        stream_types = [
            'video',
        ]

        stream_codecs = [
            'hevc',
            'h265',
        ]

        if stream_info.get('codec_type', '').lower() in stream_types and \
           stream_info.get('codec_name', '').lower() in stream_codecs:
            return True
        return False

    def custom_stream_mapping(self, stream_info: dict, stream_id: int):
        return {
            'stream_mapping':  [ ],
            'stream_encoding': [ ],
        }

    
def on_library_management_file_test(data):
    """
    Runner function - enables additional actions during the library management file tests.

    The 'data' object argument includes:
        path                            - String containing the full path to the file being tested.
        issues                          - List of currently found issues for not processing the file.
        add_file_to_pending_tasks       - Boolean, is the file currently marked to be added to the queue for processing.

    :param data:
    :return:

    """
    # Get the path to the file
    abspath = data.get('path')

    # Get file probe
    probe = ffmpeg.Probe.init_probe(data, logger)
    if not probe or not probe.file(abspath):
        # File probe failed, skip the rest of this test
        return data

    # Only mp4s are affected
    if not 'mp4' in probe.get('format', {}).get('format_name', [ ]):
        logger.debug("File '{}' is type '{}' - plugin requires mp4.".format(abspath, probe.get('format', {}).get('format_name', [ ])))
        return data
        
    # Only with RARBG in the title
    if not 'rarbg' in probe.get('format', {}).get('tags', {}).get('title', '').lower():
        logger.debug("Title '{}' does not indicate a RARBG h265 encoding.".format(probe.get('format', {}).get('tags', {}).get('title', '').lower()))
        return data

    # Configure settings object (maintain compatibility with v1 plugins)
    if data.get('library_id'):
        settings = Settings(library_id=data.get('library_id'))
    else:
        settings = Settings()

    # Get stream mapper
    mapper = PluginStreamMapper()
    mapper.set_settings(settings)
    mapper.set_probe(probe)

    if mapper.streams_need_processing():
        # Mark this file to be added to the pending tasks
        data['add_file_to_pending_tasks'] = True
        logger.debug("File '{}' should be added to task list.".format(abspath))
    else:
        logger.debug("File '{}' does not match criteria for processing.".format(abspath))

    return data


def on_worker_process(data):
    """
    Runner function - enables additional configured processing jobs during the worker stages of a task.

    The 'data' object argument includes:
        worker_log              - Array, the log lines that are being tailed by the frontend. Can be left empty.
        library_id              - Number, the library that the current task is associated with.
        exec_command            - Array, a subprocess command that Unmanic should execute. Can be empty.
        command_progress_parser - Function, a function that Unmanic can use to parse the STDOUT of the command to collect progress stats. Can be empty.
        file_in                 - String, the source file to be processed by the command.
        file_out                - String, the destination that the command should output (may be the same as the file_in if necessary).
        original_file_path      - String, the absolute path to the original file.
        repeat                  - Boolean, should this runner be executed again once completed with the same variables.

    :param data:
    :return:
    
    """

    # This plugin requires multiple passes to perform the correction:
    #
    #     1. Split mp4 into video and audio mkvs
    #     2. Reprocess video mkv (with mkvtoolnix)
    #     3. Reprocess audio mkv (with mkvtoolnix)
    #     4. Recombine video and audio into mp4

    # Get file paths
    abspath = data.get('file_in')
    basename = data['file_out'].rpartition('.')[0].rpartition('-WORKING-')[0]
    pass_num = data.get('pass_num', 1)
    
    logger.debug("Pass_Num is: '%d'" % (pass_num))
    logger.debug(" Abspath is: '%s'" % (abspath))
    logger.debug("Basename is: '%s'" % (basename))

    # Get file probe
    probe = ffmpeg.Probe(logger, allowed_mimetypes=['video'])
    if not probe or not probe.file(abspath):
        # File probe failed, skip the rest of this test
        logger.warning("File '{}' doesn't exist or can't be probed.".format(abspath))
        return data

    # Configure settings object (maintain compatibility with v1 plugins)
    if data.get('library_id'):
        settings = Settings(library_id=data.get('library_id'))
    else:
        settings = Settings()

    # Get stream mapper
    mapper = PluginStreamMapper()
    mapper.set_settings(settings)
    mapper.set_probe(probe)

    # Set the parser
    parser = ffmpeg.Parser(logger)

    # Split
    if pass_num == 1:
        # Only perform file type/codec/title tests on first pass
        #
        
        # Only mp4s
        if not 'mp4' in probe.get('format', {}).get('format_name', [ ]):
            logger.debug("File '{}' is type '{}' - plugin requires mp4.".format(abspath, probe.get('format', {}).get('format_name', [ ])))
            return data

        # Only if it's HEVC
        if not mapper.streams_need_processing():
            logger.info("No streams in this file match the processing criteria")
            return data

        # Only with RARBG in the title
        if not 'rarbg' in probe.get('format', {}).get('tags', {}).get('title', '').lower():
            logger.debug("Title '{}' does not indicate a RARBG h265 encoding.".format(probe.get('format', {}).get('tags', {}).get('title', '').lower()))
            return data

        data['repeat'] = True
        data['pass_num'] = 2
        data['file_out'] = "%s.rarbg_video.mkv" % (basename)
        
        mapper.set_input_file(abspath)
        mapper.set_output_file(data.get('file_out'))

        exec_args = [
            '-y',
            '-i', abspath,
            '-map', '0:v',
            '-map', '0:s?',
            '-c:v', 'copy',
            data['file_out'],
            '-map', '0:a',
            '-c:a', 'copy',
            "%s.rarbg_audio.mkv" % (basename)
        ]
        data['exec_command'] = ['ffmpeg']
        data['exec_command'] += exec_args

    # Reprocess video with mkvmerge
    elif pass_num == 2:
        data['repeat'] = True
        data['pass_num'] = 3
        # override file_in
        data['file_in'] = "%s.rarbg_video.mkv" % (basename)
        data['file_out'] = "%s.rarbg_video_fixed.mkv" % (basename)

        mapper.set_input_file(abspath)
        mapper.set_output_file(data.get('file_out'))

        exec_args = [
            '-A',
            '-S',
            '-o', data['file_out'],
            data['file_in']
        ]
        data['exec_command'] = ['mkvmerge']
        data['exec_command'] += exec_args
        
        # Override the parser
        parser = mkvtoolnix.Parser(logger)

    # Reprocess audio with mkvmerge
    elif pass_num == 3:
        data['repeat'] = True
        data['pass_num'] = 4
        # override file_in
        data['file_in'] = "%s.rarbg_audio.mkv" % (basename)
        data['file_out'] = "%s.rarbg_audio_fixed.mkv" % (basename)

        mapper.set_input_file(data['file_in'])
        mapper.set_output_file(data.get('file_out'))

        exec_args = [
            '-D',
            '-o', data['file_out'],
            data['file_in']
        ]
        # Apply ffmpeg args to command
        data['exec_command'] = ['mkvmerge']
        data['exec_command'] += exec_args
        
        # Override the parser
        parser = mkvtoolnix.Parser(logger)

    # Recombine (Final pass)
    elif pass_num == 4:
        data['repeat'] = False
        data['file_out'] = "%s.rarbg_fixed.mp4" % (basename)

        mapper.set_input_file(abspath)
        mapper.set_output_file(data.get('file_out'))

        exec_args = [
            '-y',
            '-i', "%s.rarbg_video_fixed.mkv" % (basename),
            '-i', "%s.rarbg_audio_fixed.mkv" % (basename),
            '-c', 'copy',
            '-map', '0', '-map', '1',
            data['file_out']
        ]
        data['exec_command'] = ['ffmpeg']
        data['exec_command'] += exec_args

    parser.set_probe(probe)
    data['command_progress_parser'] = parser.parse_progress

    return data

