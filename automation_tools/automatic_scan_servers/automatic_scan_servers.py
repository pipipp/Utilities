"""
Use SSH to remotely scan all Apollo server program mapping and program release versions and apollo package versions
All scan results are written to the CSV file and saved to the current path,
and you can also email to the designated cisco mailbox

Use crontab to run Python programs regularly on a Linux system
===================================================================
Basic command:
crontab -e    Open the VI compiler and enter the command to execute
crontab -l    View the status of all tasks performed
crontab -r    Delete all executing tasks

Query task execution log:
cat /var/spool/mail/{enter your username}

Use examples:
1. Open the terminal window and enter "crontab -e" into VI edit mode
2. Type the command [usage: minute   hour   day   month   week   command]
   0 8 * * 1 /usr/local/bin/python /tftpboot/automatic_scan_servers.py (It starts every Monday at 8 a.m)
3. Save and exit when you have finished typing
4. Type "crontab -l" to see the tasks that have been executed and confirm that they were executed successfully
===================================================================
"""
# !/usr/local/bin/python2.7
# -*- coding:utf-8 -*-
# @Time     : 2019/06/05
# @Author   : Evan Liu
# @Python   : 2.7
# @System   : Linux

import sys
sys.path.append('/opt/cisco/constellation')
import os
import re
import time
import pandas
import threading

from apollo.libs import lib
from pexpect import pxssh


class ProgramMappingScan(object):

    def __init__(self, account_info, machine_config_path, thread_pool_max=100):
        self.account_info = account_info
        self.machine_config_path = machine_config_path
        self.thread_pool = threading.Semaphore(value=thread_pool_max)
        self.save_file_name = 'machine_config_mapping_scan_results.csv'
        self.all_machine_info = {}
        self.scan_result = []
        self.config_mapping_check_cmd = [
            ['cd /opt/cisco/constellation/apollo/scripts/wnbu', 'trunk -> /opt/cisco/scripts/prod/wnbu/trunk'],
            ['cd /opt/cisco/constellation/apollo/config', '/opt/cisco/constellation/apollo/scripts/wnbu/trunk/trunk/']
        ]

    def read_all_machine_info(self, machine_file):
        """
        Read local all machine configuration info
        :param machine_file: machine configuration file
        :return:
        """
        if 'fx' in machine_file:
            if '_' in machine_file:
                machine_name = machine_file.split('_')[0]
            else:
                machine_name = machine_file.split('.')[0]

            with open('{}/{}'.format(self.machine_config_path, machine_file), 'r') as rf:
                data = rf.read()

            product_line = re.search("PRODUCT_LINE = '(.+?)'", data)
            test_area = re.search("TEST_AREA = '(.+?)'", data)

            if not self.all_machine_info.get(machine_name):
                self.all_machine_info[machine_name] = {}
                if not self.all_machine_info[machine_name].get('Product_line'):
                    self.all_machine_info[machine_name]['Product_line'] = []
                if not self.all_machine_info[machine_name].get('Test_area'):
                    self.all_machine_info[machine_name]['Test_area'] = []

            self.all_machine_info[machine_name]['Product_line'].append(product_line.group(1))
            self.all_machine_info[machine_name]['Test_area'].append(test_area.group(1))

    def process(self, machine_name):
        with self.thread_pool:
            self.machine_config_mapping_scan(machine_name=machine_name)

    def machine_config_mapping_scan(self, machine_name):
        """Start scan"""
        result = {}
        for i in range(3):
            try:
                # Connect to apollo server
                s = pxssh.pxssh()
                s.login(machine_name, self.account_info[0], self.account_info[1])

                # Check the machine config mapping
                for index, data in enumerate(self.config_mapping_check_cmd):
                    cmd = data[0]
                    s.sendline(cmd)
                    s.prompt()
                    s.sendline('ls -l')
                    s.prompt()

                    # capture all config mappings
                    redundant = ''
                    redundant_mapping = []
                    config_mapping = re.findall(r'\w+\.?\w+ -> .+', s.before)
                    if config_mapping:
                        for each_line in config_mapping:
                            # capture redundant mapping
                            if data[1] not in each_line:
                                redundant_mapping.append(each_line)
                        all_mapping = '{}: {}\n'.format(index+1, cmd) + 'result: ' + ',\n'.join(config_mapping)
                    else:
                        all_mapping = '{}: {}\nNot found any configuration mapping'.format(index+1, cmd)

                    if redundant_mapping:
                        redundant = '{}: {}\n'.format(index + 1, cmd) + 'result: ' + ',\n'.join(redundant_mapping)

                    for field, value in zip(['Redundant_mapping', 'All_config_mapping'], [redundant, all_mapping]):
                        if value:
                            if result.get(field):
                                result[field] = result[field] + '\n' + value
                            else:
                                result[field] = value

                # capture prod package version
                s.sendline('apollo packages')
                s.prompt()
                received = s.before.splitlines()
                if received:
                    links = [i.strip() for i in received[3:] if i.strip()]
                    result['Package_version'] = ',\n'.join(links[:-2])
                else:
                    result['Package_version'] = 'Not found'

                # capture apollo version
                s.sendline('apollo version')
                s.prompt()
                line = re.search(r'Apollo-\d+-\d+', s.before)
                if line:
                    result['Apollo_version'] = line.group()
                else:
                    result['Apollo_version'] = 'Not found'

                s.logout()
                break
            except Exception as ex:
                if i == 2 or 'Could not establish connection to host' in ex.message:
                    result['Error_info'] = ex.message
                    break
                time.sleep(2)

        result['Station'] = machine_name
        self.scan_result.append(result)
        print('Station: {}, scan ok!'.format(machine_name))

    def save_data(self):
        """Write file to csv"""
        items = {}
        columns = ['Station', 'Test_area', 'Product_line', 'All_config_mapping',
                   'Redundant_mapping', 'Package_version', 'Apollo_version', 'Error_info']
        for i in columns:
            items[i] = []
        for each in self.scan_result:
            items['Station'].append(each['Station'])
            items['Test_area'].append(self.all_machine_info[each['Station']]['Test_area'])
            items['Product_line'].append(self.all_machine_info[each['Station']]['Product_line'])
            items['All_config_mapping'].append(each.get('All_config_mapping', 'empty'))
            items['Redundant_mapping'].append(each.get('Redundant_mapping', 'empty'))
            items['Package_version'].append(each.get('Package_version', 'empty'))
            items['Apollo_version'].append(each.get('Apollo_version', 'empty'))
            items['Error_info'].append(each.get('Error_info', 'empty'))
        data = pandas.DataFrame(items, columns=columns)
        data.to_csv(self.save_file_name, index=False)

    def main(self):
        for machine_file in os.listdir(self.machine_config_path):
            self.read_all_machine_info(machine_file)
        print('The total number of machines is [{}]'.format(len(self.all_machine_info)))

        threads = []
        for each_machine in self.all_machine_info.keys():
            t = threading.Thread(target=self.process, args=(each_machine,))
            threads.append(t)

        print('Running...')
        for i in threads:
            i.start()

        for i in threads:
            i.join()

        print('Scan completed!')
        if self.scan_result:
            self.save_data()

    def send_email(self, mails):
        """Send email to cisco mailbox"""
        for email in mails:
            if os.path.exists(self.save_file_name):
                lib.sendmail(to=email, subject='Machine config mapping scan results',
                             body='all the scan machines result is in the attachment, Please review, Thanks!',
                             attachments=self.save_file_name)
                print('send email to ({}) mailbox successful!'.format(email))
            else:
                print('The csv file [{}] is not found, please check!'.format(self.save_file_name))
        # Delete the local csv file
        if os.path.exists(self.save_file_name):
            os.remove(self.save_file_name)


if __name__ == '__main__':
    username = raw_input('Please enter your username: ')
    password = raw_input('Please enter your password: ')
    machine_config_file_path = '/opt/cisco/scripts/prod/wnbu/trunk/trunk/stations/foc'
    handle = ProgramMappingScan(account_info=(username, password),
                                machine_config_path=machine_config_file_path, thread_pool_max=150)
    handle.main()
