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

# pylint: disable=E1101

""" System Status Analaysis Module """

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt

from analysis_module import AnalysisModule


class StatusAnalysis(AnalysisModule):
    """
    Support for System Status analysis

    :param trace: input Trace object
    :type trace: :mod:`libs.utils.Trace`
    """

    def __init__(self, trace):
        super(StatusAnalysis, self).__init__(trace)


###############################################################################
# DataFrame Getter Methods
###############################################################################

    def _dfg_overutilized(self):
        """
        Get data frame with sched_overutilized data.
        """
        if not self._trace.hasEvents('sched_overutilized'):
            return None

        # Build sequence of overutilization "bands"
        df = self._dfg_trace_event('sched_overutilized')

        # Remove duplicated index events, keep only last event which is the
        # only one with a non null length
        df = df[df.len != 0]
        # This filtering can also be achieved by removing events happening at
        # the same time, but perhaps this filtering is more complex
        # df = df.reset_index()\
        #         .drop_duplicates(subset='Time', keep='last')\
        #         .set_index('Time')
        columns = ['len', 'overutilized']
        if 'sd_span' in df.columns:
            columns.append('sd_span')
        return df[columns]


###############################################################################
# Plotting Methods
###############################################################################

    def cpulist_to_array(self, cpulist):
        """
        Convert a kernel-formatted cpulist to an array of cpu_ids
        """
        array = None
        try:
            array = []
            groups=cpulist.split(',')
            for g in groups:
                g_range = g.split('-')
                if len(g_range) == 1:
                    array.append(g_range[0])
                else:
                    start = int(g_range[0])
                    end = int(g_range[1])
                    for i in range(start, end+1, 1):
                        array.append(str(i))
        except:
            self._log.error("Unable to parse cpulist {}".format(cpulist))
        return array

    def plotOverutilized(self, axes=None, cpu_id=None):
        """
        Draw a plot that shows intervals of time where the system was reported
        as overutilized.

        The optional axes parameter allows to plot the signal on an existing
        graph.

        :param axes: axes on which to plot the signal
        :type axes: :mod:`matplotlib.axes.Axes`
        """
        if not self._trace.hasEvents('sched_overutilized'):
            self._log.warning('Event [sched_overutilized] not found, '
                              'plot DISABLED!')
            return

        df = self._dfg_overutilized()

        # If not axis provided: generate a standalone plot
        if not axes:
            gs = gridspec.GridSpec(1, 1)
            plt.figure(figsize=(16, 1))
            axes = plt.subplot(gs[0, 0])
            axes.set_title('System Status {white: EAS mode, '
                           'red: Non EAS mode}')
            axes.set_xlim(self._trace.x_min, self._trace.x_max)
            axes.set_yticklabels([])
            axes.set_xlabel('Time [s]')
            axes.grid(True)

        # Compute intervals in which the system is reported to be overutilized
        if not 'sd_span' in df.columns:
            # this trace has whole-system overutilized
            bands = [(t, df['len'][t], df['overutilized'][t]) for t in df.index]
            # plot the bands
            for (start, delta, overutilized) in bands:
                if not overutilized:
                    continue
                end = start + delta
                axes.axvspan(start, end, facecolor='r', alpha=0.1)
        else:
            # this trace has per-sched-domain overutilization
            # only show overutilized status when a domain includes the
            # cpu we are passing
            sd_spans = list(df.sd_span.unique())
            # sort the bands by the number of CPUs in the group
            sd_spans.sort(key=lambda x: len(self.cpulist_to_array(x)))
            # try to match colors across multiple graphs from same trace
            face={}
            colors=['r','g','b']
            color_idx = 0
            for span in sd_spans:
                face[span] = colors[color_idx % len(colors)]
                color_idx += 1
                array = self.cpulist_to_array(span)
                if not array:
                   continue
                if cpu_id and str(cpu_id) not in array:
                   self._log.warning("Plotting for CPU {}: Skipping overutilized data for {}".format(cpu_id, span))
                   continue
                bands = [(t, df.loc[t]['len'], df.loc[t]['overutilized']) for t in df[df.sd_span == span].index]

                self._log.warning('cpu_id {} : span {} is color {}'.format(cpu_id, span, face[span]))
                for (start, delta, overutilized) in bands:
                    try:
                        if not overutilized:
                            continue
                    except ValueError:
                        # If we have multiple entries with the same index we get here
                        self._log.warning('multiple overutilized events at {}'.format(start))
                        delta = delta.iloc[0]
                        overutilized = overutilized.iloc[0]
                        if not overutilized:
                            continue
                    end = start + delta
                    axes.axvspan(start, end, facecolor=face[span], alpha=0.1)

# vim :set tabstop=4 shiftwidth=4 expandtab
