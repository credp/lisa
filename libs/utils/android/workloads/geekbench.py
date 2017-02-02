# SPDX-License-Identifier: Apache-2.0
#
# Copyright (C) 2015, ARM Limited and contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import re
import os
import logging

from subprocess import Popen, PIPE
from android import Screen, Workload, System
from time import sleep


class Geekbench(Workload):
    """
    Android Geekbench workload
    """

    # Package required by this workload
    package = 'com.primatelabs.geekbench'
    activity = '.HomeActivity'

    def __init__(self, test_env):
        super(Geekbench, self).__init__(test_env)
        self._log = logging.getLogger('Geekbench')
        self._log.debug('Workload created')

    def run(self, exp_dir, collect=''):

        # Initialize energy meter results
        nrg_report = None

        # Regexps for benchmark synchronization
        end_logline = r'GEEKBENCH_RESULT: (.*)'
        GEEKBENCH_BENCHMARK_END_RE = re.compile(end_logline)
        self._log.debug("END string [%s]", end_logline)

        # Clear the stored data for the application, so we always start with
        # an EULA to clear
        self._target.execute('pm clear {}'.format(self.package))

        # Clear logcat from any previous runs
        # do this on the target as then we don't need to build a string
        self._target.execute('logcat -c')

        # Unlock device screen (assume no password required)
        System.menu(self._target)
        # Press Back button to be sure we run the video from the start
        System.back(self._target)

        # Force screen in PORTRAIT mode
        Screen.set_orientation(self._target, portrait=True)

        # Start app on the target device
        System.start_activity(self._target, self.package, self.activity)
        # Allow the activity to start
        sleep(1)

        # Parse logcat output lines to find the end
        logcat_cmd = self._adb(
                'logcat ActivityManager:* System.out:I *:S GEEKBENCH_RESULT:*'\
                .format(self._target.adb_name))
        self._log.info("%s", logcat_cmd)

        # Click to accept the EULA
        System.tap(self._target, 73, 55)
        sleep(1)

        # Press the 'RUN CPU BENCHMARK' button
        System.tap(self._target, 73, 72)

        # Start energy collection
        if 'energy' in collect and self.te.emeter:
            self.te.emeter.reset()

        # Wait for the benchmark to end
        logcat = Popen(logcat_cmd, shell=True, stdout=PIPE)
        while True:

            # read next logcat line (up to max 1024 chars)
            message = logcat.stdout.readline(1024)

            # Benchmark start trigger
            match = GEEKBENCH_BENCHMARK_END_RE.search(message)
            if match:
                remote_result_file = match.group(1)
                self._log.debug("Benchmark finished! Results are in {}".format(remote_result_file))
                break

        self._log.debug("Benchmark done!")

        # Stop energy collection
        if 'energy' in collect and self.te.emeter:
            nrg_report = self.te.emeter.report(exp_dir)

        # Get Geekbench Results file
        local_result_file = os.path.basename(remote_result_file)
        result_file = os.path.join(self.te.res_dir, local_result_file)
        self._log.debug("result_file={}".format(result_file))
        self._target.pull(remote_result_file, result_file)

        # Close the app
        System.force_stop(self._target, self.package, clear=False)

        # Go back to home screen
        System.home(self._target)

        # Switch back to screen auto rotation
        Screen.set_orientation(self._target, auto=True)

        return result_file, nrg_report

# vim :set tabstop=4 shiftwidth=4 expandtab
