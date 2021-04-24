# -*- coding:utf-8 -*-
import re
import os
import pandas

from collections import OrderedDict
from lxml import etree


class EndReportParse(object):

    def __init__(self, filepath):
        self.filepath = filepath  # HTML file path
        self.file_name = filepath.split('\\')[-1].split('.html')[0]  # The name used for Excel saving
        self.storage_folder = 'result'  # Storage folder name
        self.data = None
        self.step_info = None
        self.final_data = []

    def read_html_file(self):
        """Read html file data to string"""
        with open(self.filepath, 'r') as rf:
            self.data = rf.read()

    def capture_step_info(self, html_node):
        """
        capture each step information
        :param html_node:
        :return:
        """
        self.step_info = OrderedDict(
            test_step_name='',
            seq_name='',
            test_step_status='',
            test_step_time='',
            module_path='',
            func_name='',
            sent_info='',
        )

        # Capture test_step_name
        test_step_name = re.search('Step "(.+?)"', html_node.xpath('table/caption/span/text()')[0])
        if test_step_name:
            self.step_info['test_step_name'] = test_step_name.group(1).strip()

        # Capture test_step_status
        test_step_status = html_node.xpath('table/caption/span/strong/text()')
        if test_step_status:
            self.step_info['test_step_status'] = test_step_status[0].strip()

        # Capture test_step_time
        test_step_time = html_node.xpath('table/caption/span/text()')
        if test_step_time:
            self.step_info['test_step_time'] = test_step_time[1].split()[1].strip()

        # Capture seq_name
        seq_name = html_node.xpath('table/tbody/tr[4]/td/text()')
        if seq_name:
            if '|' in seq_name[0].strip():
                self.step_info['seq_name'] = seq_name[0].strip()

        # Capture module_path
        module_path = html_node.xpath('table/tbody/tr[5]/td/text()')
        if module_path:
            self.step_info['module_path'] = module_path[0].strip()

        # Capture func_name
        func_name = html_node.xpath('table/tbody/tr[6]/td/text()')
        if func_name:
            self.step_info['func_name'] = func_name[0].strip()

        # Capture sent_info
        sent_info = html_node.xpath('table/tbody/tr[10]/td/details/table/tbody/tr')
        if sent_info:
            temp = []
            for each in sent_info:
                sent_type = each.xpath('td[2]/text()')
                if sent_type and 'SENT' in sent_type[0].upper():
                    conn_name = each.xpath('td[3]/text()')[0].split('|')[-1]
                    commands = each.xpath('td[6]/text()')[0]
                    temp.append('[{}: {}]'.format(conn_name, commands))
            self.step_info['sent_info'] = ', '.join(temp)

        self.final_data.append(list(self.step_info.values()))

    def save_data(self):
        """Write data to excel"""
        if not os.path.isdir(self.storage_folder):
            os.mkdir(self.storage_folder)

        data = pandas.DataFrame(self.final_data, columns=list(self.step_info.keys()))
        data.to_excel('{}/{}.xlsx'.format(self.storage_folder, self.file_name), index=False, sheet_name='Result')

    def parse(self):
        """Parsing HTML files"""
        html = etree.HTML(self.data)
        all_step = html.xpath('//blockquote')  # Capture all step node
        for each in all_step:
            self.capture_step_info(each)

    def main(self):
        self.read_html_file()
        self.parse()
        self.save_data()


def main():
    html_file = []
    for file_name in os.listdir(os.getcwd()):  # Reads all HTML files in the current path
        if '.html' in file_name:
            html_file.append(file_name)

    for html in html_file:
        print('Start parsing the ({}) file'.format(html))
        report_parse = EndReportParse(filepath=html)
        report_parse.main()


if __name__ == '__main__':
    main()
