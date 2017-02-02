#!/usr/bin/python

import os

# The workload class MUST be loaded before the LisaBenchmark
from android import Workload
from android import LisaBenchmark

from devlib.exception import TargetError

class GeekbenchTest(LisaBenchmark):

    bm_conf = {

        # Target platform and board
        "platform"      : 'android',

        # Define devlib modules to load
        "modules"     : [
            'cpufreq',
        ],

        # FTrace events to collect for all the tests configuration which have
        # the "ftrace" flag enabled
        "ftrace"  : {
            "events" : [
                "sched_switch",
                "sched_overutilized",
                "sched_contrib_scale_f",
                "sched_load_avg_cpu",
                "sched_load_avg_task",
                "sched_tune_tasks_update",
                "sched_boost_cpu",
                "sched_boost_task",
                "sched_energy_diff",
                "cpu_frequency",
                "cpu_idle",
                "cpu_capacity",
            ],
            "buffsize" : 10 * 1024,
        },

        # Default EnergyMeter Configuration
        "emeter" : {
            "instrument" : "acme",
            "channel_map" : {
                "Device0" : 0,
            }
        },

        # Tools required by the experiments
        "tools"   : [ 'trace-cmd' ],

		# Default results folder
		"results_dir" : "AndroidGeekbench",

    }

	# Android Workload to run
    bm_kind = 'Geekbench'

	# Default products to be collected
    bm_collect = 'ftrace energy'

    def benchmarkInit(self):
        self.setupWorkload()
        return self.setupGovernor()

    def benchmarkFinalize(self):
		pass

    def __init__(self, governor):
        self.governor = governor
        super(GeekbenchTest, self).__init__()

    def setupWorkload(self):
        # Create a results folder for each "governor/test"
        self.out_dir = os.path.join(self.te.res_dir, governor)
        try:
                os.stat(self.out_dir)
        except:
                os.makedirs(self.out_dir)

    def setupGovernor(self):
        try:
            self.target.cpufreq.set_all_governors(self.governor);
        except TargetError:
            self.log.warning('Governor [%s] not available on target',
                             self.governor)
            return False
        # Setup schedutil parameters
        if self.governor == 'schedutil':
            rate_limit_us = 2000
            # Different versions of schedutil have different rate limit
            # tunables.
            tunables = self.target.cpufreq.list_governor_tunables(0)
            if 'rate_limit_us' in tunables:
                tunables = {'rate_limit_us' : str(rate_limit_us)}
            else:
                assert ('up_rate_limit_us' in tunables and
                        'down_rate_limit_us' in tunables)
                tunables = {'up_rate_limit_us' : str(rate_limit_us),
                            'down_rate_limit_us' : str(rate_limit_us)}

            try:
                for cpu_id in range(self.te.platform['cpus_count']):
                    self.target.cpufreq.set_governor_tunables(
                        cpu_id, 'schedutil', **tunables)
            except TargetError as e:
                self.log.warning(
                    'Failed to set schedutil parameters: {}'.format(e))
                return False
            self.log.info('Set schedutil.rate_limit_us=%d', rate_limit_us)
        # Setup ondemand parameters
        if self.governor == 'ondemand':
            try:
                for cpu_id in range(self.te.platform['cpus_count']):
                    tunables = self.target.cpufreq.get_governor_tunables(cpu_id)
                    self.target.cpufreq.set_governor_tunables(
                        cpu_id, 'ondemand',
                        **{'sampling_rate' : tunables['sampling_rate_min']})
            except TargetError:
                self.log.warning('Failed to set ondemand parameters')
                return False
            self.log.info('Set ondemand.sampling_rate to minimum supported')
        # Report configured governor
        governors = self.target.cpufreq.get_all_governors()
        self.log.info('Using governors: %s', governors)
        return True


# Run the benchmark in each of the supported governors

governors = [
    'performance',
    'ondemand',
    'interactive',
    'sched',
    'schedutil',
    'powersave',
]

for governor in governors:
    GeekbenchTest(governor)

# vim :set tabstop=4 shiftwidth=4 expandtab
