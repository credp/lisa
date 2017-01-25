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

import argparse
import logging
import os
import select

from subprocess import Popen, PIPE
from time import sleep

from conf import LisaLogging
from android import System, Workload
from env import TestEnv


class LisaBenchmark(object):
    """
    A base class for LISA custom benchmarks execution

    This class is intended to be subclassed in order to create a custom
    benckmark execution for LISA.
    It sets up the TestEnv and and provides convenience methods for
    test environment setup, execution and post-processing.

    Subclasses should provide a bm_conf to setup the TestEnv and
    a set of optional callback methods to configuere a test environment
    and process collected data.

    Example users of this class can be found under LISA's tests/benchmarks
    directory.
    """

    bm_conf = None
    """Override this with a dictionary or JSON path to configure the TestEnv"""

    bm_kind = None
    """Override this with the name of the LISA's benchmark to run"""

    bm_params = None
    """Override this with the set of parameters for the LISA's benchmark to run"""

    bm_collect = None
    """Override this with the set of data to collect during test exeution"""

    def benchmarkInit(self):
        """
        Code executed before running the benchmark
        """
        pass

    def benchmarkFinalize(self):
        """
        Code executed after running the benchmark
        """
        pass

################################################################################
# Private Interface

    def _parseCommandLine(self):

        parser = argparse.ArgumentParser(
                description='LISA Benchmark Configuration')

        # Bootup settings
        parser.add_argument('--boot_image', type=str,
                default=None,
                help='Path of the Android boot.img to be used')

        # Android settings
        parser.add_argument('--android_device', type=str,
                default=None,
                help='Identifier of the Android target to use')
        parser.add_argument('--android_home', type=str,
                default=None,
                help='Path used to configure ANDROID_HOME')

        # Test customization
        parser.add_argument('--results_dir', type=str,
                default=None,
                help='Results folder, '
                     'if specified override test defaults')
        parser.add_argument('--collect', type=str,
                default=None,
                help='Set of metrics to collect, '
                     'e.g. "energy systrace_30" to sample energy and collect a 30s systrace, '
                     'if specified overrides test defaults')

        # Measurements settings
        parser.add_argument('--iio_channel_map', type=str,
                default=None,
                help='List of IIO channels to sample, '
                     'e.g. "ch0:0,ch3:1" to sample CHs 0 and 3, '
                     'if specified overrides test defaults')

        # Parse command line arguments
        self.args = parser.parse_args()

    def _getBmConf(self):
        if self.bm_conf is None:
            raise NotImplementedError("Override `bm_conf` attribute")
        # Override default configuration with command line parameters
        if self.args.android_device:
            self.bm_conf['device'] = self.args.android_device
        if self.args.android_home:
            self.bm_conf['ANDROID_HOME'] = self.args.android_home
        if self.args.results_dir:
            self.bm_conf['results_dir'] = self.args.results_dir
        if self.args.collect:
            self.bm_collect = self.args.collect

        if self.args.iio_channel_map:
            try:
                em = self.bm_conf['emeter']
                if em['instrument'] != 'acme':
                    raise ValueError
                em['channel_map'] = {}
                for ch in self.args.iio_channel_map.split(','):
                    ch_name, ch_id = ch.split(':')
                    em['channel_map'][ch_name] = ch_id
                self.bm_conf['emeter'] = em
                self.log.info('Using iio-capture channels: %s', em)
            except:
                # No ACME configuration required by the test
                pass

        return self.bm_conf

    def _getBmKind(self):
        if self.bm_kind is None:
            raise NotImplementedError("Override `bm_kind` attribute")
        # Get a referench to the worload to run
        self.wl = Workload(self.te).getInstance(self.bm_kind)
        if self.wl is None:
            raise ValueError("Specified benchmark [{}] is not supported"\
                             .format(self.bm_kind))
        return self.wl

    def _getBmParams(self):
        if self.bm_params is None:
            raise NotImplementedError("Override `bm_params` attribute")
        return self.bm_params

    def _getBmCollect(self):
        if self.bm_collect is None:
            self.log.warning('No data collection configured')
            return ''
        return self.bm_collect

    def __init__(self):
        """
        Set up logging and trigger running experiments
        """
        LisaLogging.setup()
        self.log = logging.getLogger('Benchmark')

        self.log.info('=== CommandLine parsing...')
        self._parseCommandLine()

        self.log.info('=== TestEnv setup...')
        self.te = TestEnv(self._getBmConf())
        self.target = self.te.target
        # TODO: Check if TestEnv already provides support for rebooting
        self._reboot()

        self.log.info('=== Initialization...')
        self._getBmKind()
        self.out_dir=self.te.res_dir
        if not self.benchmarkInit():
            self.log.debug('Initialization failed: execution aborted')
            return

        self.log.info('=== Execution...')
        self.wl.run(out_dir=self.out_dir,
                    collect=self._getBmCollect(),
                    **self.bm_params)

        self.log.info('=== Finalization...')
        self.benchmarkFinalize()

    def _adb(self, cmd):
        os.system('adb -s {} {}'.format(self.target.adb_name, cmd))

    def _fastboot(self, cmd):
        os.system('fastboot -s {} {}'.format(self.target.adb_name, cmd))


    def _wait_for_logcat_idle(self, seconds=1):
        lines = 0

        # Clear logcat
        # os.system('{} logcat -s {} -c'.format(adb, DEVICE));
        self._adb('logcat -c')

        # Dump logcat output
        logcat_cmd = 'adb -s {} logcat'.format(self.target.adb_name)
        logcat = Popen(logcat_cmd, shell=True, stdout=PIPE)
        logcat_poll = select.poll()
        logcat_poll.register(logcat.stdout, select.POLLIN)

        # Monitor logcat until it's idle for the specified number of [s]
        self.log.info('Waiting for system to be almost idle')
        self.log.info('   i.e. at least %d[s] of no logcat messages', seconds)
        while True:
            poll_result = logcat_poll.poll(seconds * 1000)
            if not poll_result:
                break
            lines = lines + 1
            line = logcat.stdout.readline(1024)

    def _reboot(self):

        # Reboot the device, if a boot_image has been specified
        if self.args.boot_image:

            self.log.warning('=== Rebooting...')
            self.log.warning('Rebooting image to use: %s', self.args.boot_image)

            self.log.debug('Waiting 6[s] to enter bootloader...')
            self._adb('reboot-bootloader')
            sleep(6)
            self._fastboot('boot {}'.format(self.args.boot_image))

            self.log.debug('Waiting 20[s] for boot to start...')
            sleep(20)

        else:
            self.log.warning('Device NOT rebooted, using current image')

        # Restart ADB in root mode
        self._adb('root')

        # TODO add check for kernel SHA1

        # Disable charge via USB
        self.log.debug('Disabling charge over USB...')
        self._adb('shell "echo 0 >/sys/class/power_supply/battery/charging_enabled"')

        # Log current kernel version
        output = self.target.execute('uname -a')
        self.log.info('Running with kernel:')
        self.log.info('   %s', output)

        # Wait for the system to complete the boot
        self._wait_for_logcat_idle()

# vim :set tabstop=4 shiftwidth=4 expandtab
