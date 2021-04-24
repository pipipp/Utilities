"""
Unit test log download feature
"""
# -*- coding:utf-8 -*-
# @Time     : 2020/03/21
# @Author   : Evan Liu
# @Python   : 3.7

import os
import re
import json
import time
import html
import base64
import requests
import threading


class CCCSpider(object):

    def __init__(self, login_account=(), thread_pool_max=10):
        self.login_account = login_account
        self.download_results = []
        self.thread_pool = threading.Semaphore(value=thread_pool_max)
        self.root_url = 'https://cesium.cisco.com/apps/cesiumhome/overview'
        self.verification_source_url = 'https://api-dbbfec7f.duosecurity.com'
        self.verification_prompt_url = self.verification_source_url + '/frame/prompt'
        self.verification_status_url = self.verification_source_url + '/frame/status'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)'
                          ' Chrome/80.0.3987.132 Safari/537.36'
        })
        self.build_storage_folder()

    @staticmethod
    def build_storage_folder():
        # Create a folder to store all the download results
        if not os.path.isdir('download_results'):
            os.mkdir('download_results')
        os.chdir('download_results')

    def login(self, authentication_code=''):
        """
        Login to the CCC website
        :param authentication_code: Fill in the Mobile pass code
        :return:
        """
        resp = self.session.get(self.root_url)
        if '302' in str(resp.history):  # Redirect to the account login interface
            login_url = re.search('name="login-form" action="(.+?)"', resp.text)
            data = {
                'pf.username': self.login_account[0],
                'pf.pass': self.login_account[1],
                'pf.userType': 'cco',
                'pf.TargetResource': '?'
            }
            resp = self.session.post(login_url.group(1), data=data)
            if resp.status_code == 200:
                # Enter the authentication interface "Two-Factor Authentication"
                sig_request = re.search("'sig_request': '(.+?)(:APP.+?)'", resp.text)
                post_action = re.search("'post_action': '(.+?)'", resp.text)
                referer = 'https://cloudsso.cisco.com/' + post_action.group(1)
                duo_security_url = 'https://api-dbbfec7f.duosecurity.com/frame/web/v1/auth?'
                authentication_url = '{}tx={}&parent={}&v={}'.format(duo_security_url, sig_request.group(1),
                                                                     referer, '2.6')
                data = {
                    'tx': sig_request.group(1),
                    'parent': referer,
                    'referer': referer,
                    'screen_resolution_width': '1920',
                    'screen_resolution_height': '1080',
                    'color_depth': '24',
                    'is_cef_browser': 'false',
                    'is_ipad_os': 'false',
                    'react_support': 'True'
                }
                # Request for certification --> https://api-dbbfec7f.duosecurity.com/frame/web/v1/auth?
                resp = self.session.post(authentication_url, data=data)

                # 2020/11/12 update，Due to authentication interface upgrade
                if resp.status_code == 200:  # Gets multiple authentication parameters to start authentication
                    capture_params = ['sid', 'akey', 'txid', 'response_timeout', 'parent',
                                      'duo_app_url', 'eh_service_url', 'eh_download_link', 'is_silent_collection']
                    verify_param_dict = {}
                    for param in capture_params:
                        regex = r'type="hidden" name="{}" value="?(.+?)"?\s?/?>'.format(param)
                        matched = html.unescape(re.search(regex, resp.text).group(1))  # Unescape HTML
                        verify_param_dict[param] = matched

                    resp = self.session.post(authentication_url, data=verify_param_dict)
                    if '302' in str(resp.history):  # Redirect into the mobile phone verification interface
                        data = {
                            'sid': verify_param_dict['sid'],
                            'device': 'phone1',
                            'factor': 'Passcode',  # Use mobile pass code login
                            'passcode': authentication_code,
                            'out_of_date': 'False',
                            'days_out_of_date': '0',
                            'days_to_block': 'None'
                        }
                        # data = {
                        #     'sid': verify_param_dict['sid'],
                        #     'device': 'phone1',
                        #     'factor': 'Duo Push',  # Use mobile phone to push login
                        #     'dampen_choice': 'true',
                        #     'out_of_date': 'False',
                        #     'days_out_of_date': '0',
                        #     'days_to_block': 'None'
                        # }
                        # Start validation
                        resp = self.session.post(self.verification_prompt_url, data=data)
                        if resp.status_code == 200:
                            # input('Please use your mobile phone to verify the login request'
                            #       ' [Press enter to continue after verification]: ')
                            data = {
                                'sid': verify_param_dict['sid'],
                                'txid': resp.json()['response']['txid']
                            }
                            # Get validation results
                            resp = self.session.post(self.verification_status_url, data=data)
                            if resp.status_code == 200:
                                status_result_url = self.verification_source_url + resp.json()['response']['result_url']
                                data = {
                                    'sid': verify_param_dict['sid'],
                                }
                                # Gets the cookie for the validation result
                                resp = self.session.post(status_result_url, data=data)
                                if resp.status_code == 200:
                                    authentication_url = resp.json()['response']['parent']
                                    sig_response = resp.json()['response']['cookie']
                                    data = {
                                        'sig_response': sig_response + sig_request.group(2)
                                    }
                                    # Retrieve the cookie and re-enter the authentication interface
                                    self.session.post(authentication_url, data=data)
                                    # Carry the authenticated cookie acquisition Token
                                    token_url = 'https://cesium.cisco.com/apps/machineservices/MachineDetails.svc/getToken'
                                    resp = self.session.get(token_url)
                                    token = resp.json()['session']
                                    # Adds a token to the crawler
                                    self.session.headers.update({
                                        'csession': token,
                                        '_csession': token
                                    })

    def set_ccc_login_cookies(self, login_cookie, login_session):
        """
        Manually add cookie and session to the crawler
        :param login_cookie: Manually enter the CCC website and copy the cookie to here
        :param login_session: Manually enter the CCC website and copy the session to here
        :return:
        """
        self.session.headers.update({
            'csession': login_session,
            '_csession': login_session
        })
        self.session.cookies.update(self.cookie_format_conversion(login_cookie))

    @ staticmethod
    def cookie_format_conversion(raw_cookies=''):
        """
        Convert the cookies to dict type
        :param raw_cookies:
        :return:
        """
        cookies = {}
        for line in raw_cookies.split(';'):
            name, value = line.strip().split('=', 1)
            cookies[name] = value
        return cookies

    def login_ccc(self, automatic_login=True, authentication_code=''):
        """
        Login to the CCC website
        :param bool automatic_login: If the value is False, you need to manually add cookie and cession to crawler
        :param str authentication_code: Fill in the Mobile pass code
        :return:
        """
        if automatic_login:
            try:
                self.login(authentication_code=authentication_code)
            except Exception as ex:
                raise ValueError(f'Please check whether the login account and mobile pass code are correct'
                                 f' or website may be upgraded\nException info: {ex}')
        else:
            print('You need to login the CCC website and press F12 to open the "developer tools" '
                  'and manually copy the "cookie" and "csession" values to start the crawler')
            while True:
                cookie = input('cookie: ')
                session = input('csession: ')
                if not cookie or not session:
                    print('!!! cookie or csession are empty, please fill in again')
                    continue

                try:
                    self.set_ccc_login_cookies(login_cookie=cookie, login_session=session)
                except Exception:
                    print('!!! The cookie format is incorrect: {}\nplease fill in again'.format(cookie))
                    continue
                break

        # Login token double check
        if not self.session.headers.get('csession') or not self.session.headers.get('_csession'):
            raise ValueError('The mobile pass code expires or website may be upgraded\nPlease fill in again!')
        print('Login CCC website successfully')

    def get_all_test_data(self, data={}):
        """
        Gets all crawl results after the request
        :param data: Fill in the request data for spider
        :return:
        """
        multi_search_url = 'https://cesium.cisco.com/polarissvcs/central_data/multi_search'
        resp = self.session.post(multi_search_url, data=json.dumps(data))
        if resp.status_code == 200:
            return resp.json()
        else:
            return None

    def get_measurement_data(self, serial_number='', download_file_list=[], request_params={}):
        """
        Gets the specified measurement file for the specified serial number
        :param str serial_number: Test serial number
        :param list download_file_list: Fill in the specified file type to download
        :param dict request_params: Fill in the request params for spider
        :return: (measurement type, measurement id)
        """
        measures_url = 'https://cesium.cisco.com/svclnx/cgi-bin/central_cs/services.py/meas/{}'.format(serial_number)
        resp = self.session.get(measures_url, params=request_params)
        if resp.status_code == 200:
            measures_data = resp.json()
            for each_data in measures_data['measurements']:  # Walk through each measurement file
                for file_type in download_file_list:
                    limit_name = file_type.get('limit_name', '')
                    step_id = file_type.get('test_step_id', '')
                    if limit_name and step_id:
                        # Matches the specified file type
                        if limit_name == each_data['name'] and step_id == each_data['step_id']:
                            file_info = '{}_{}'.format(limit_name, step_id)
                            yield file_info, each_data['measurement']  # return the measurement type and id for download
                    else:
                        # Matches the specified file type
                        if limit_name == each_data['name']:
                            # return the measurement type and id for download
                            yield limit_name, each_data['measurement']
            else:
                yield None

    def download_measurement_log(self, file_name='measurement.log', binary_id=''):
        """
        Download the measurement log to local
        :param file_name: Log file name
        :param binary_id: Measurement log id
        :return:
        """
        download_url = 'https://cesium.cisco.com/svclnx/cgi-bin/central_cs/services.py/binarymeas_data/run'
        data = {
            'binary_id': binary_id,
            'source': 'Apollo'
        }
        flag = False
        resp = self.session.post(download_url, data=json.dumps(data))
        if resp.status_code == 200:
            content = base64.b64decode(resp.text)  # Base64 decode
            with open(file_name, 'wb') as wf:
                wf.write(content)  # Write measurement log
            flag = True
        return flag

    def get_measurement_log_file(self, measurement_data, download_file_list=[]):
        """
        Get measurement log file
        :param dict measurement_data: Measurement data
        :param list download_file_list: Fill in the specified file type to download
        :return:
        """
        with self.thread_pool:  # Controls the number of thread pools
            serial_number = measurement_data['sernum']
            params = {
                'area': measurement_data['area'],
                'server': 'prod',
                'timeid': measurement_data['tst_id'],
                'uuttype': measurement_data['uuttype']
            }
            for measures in self.get_measurement_data(serial_number=serial_number,
                                                      download_file_list=download_file_list,
                                                      request_params=params):
                if measures:
                    test_time = measurement_data['rectime'].replace(' ', '_').replace(':', '-')
                    test_status = measurement_data['attributes'].get('TEST') or 'PASS'
                    if ':' in test_status:
                        test_status = test_status.split(':')[0]
                    # Log name = 'ApolloServer - SN - TestTime - TestStatus - MeasuresType.log'
                    log_name = '{}_{}_{}_{}_{}.log'.format(measurement_data['machine'], serial_number,
                                                           test_time, test_status, measures[0])
                    # Skip duplicate test logs
                    if log_name in self.download_results:
                        continue
                    # Download the test log file
                    flag = self.download_measurement_log(file_name=log_name, binary_id=measures[1])
                    if flag:
                        self.download_results.append(log_name)
                        print('Download the file << {} >> succeeded'.format(log_name))
                    else:
                        # If download the test log fail, try again
                        time.sleep(1)
                        flag = self.download_measurement_log(file_name=log_name, binary_id=measures[1])
                        if flag:
                            self.download_results.append(log_name)
                            print('Download the file << {} >> succeeded'.format(log_name))
                        else:
                            print('Download the file << {} >> failed !!!')

    @staticmethod
    def input_info_check(check_data, download_file_list):
        """
        Check all input info
        :param check_data:
        :param download_file_list:
        :return:
        """
        # Check download file format
        assert isinstance(download_file_list, list), 'download_file_list should be of list type'
        for each in download_file_list:
            if not isinstance(each, dict):
                raise ValueError('The element in the download file list should be a dictionary type')
            if not each.get('limit_name'):
                raise ValueError('limit_name ({}) cannot be empty'.format(each))

        # Check passfail format
        check_data['passfail'] = check_data['passfail'].upper()
        if 'A' not in check_data['passfail'] and 'F' not in check_data['passfail'] and 'P' not in check_data['passfail']:
            raise ValueError('The passfail ({}) input is incorrect'.format(check_data['passfail']))

        # Check start time and end time
        if check_data['start_time'] and check_data['end_time']:
            time_format = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')
            for i in [check_data['start_time'], check_data['end_time']]:
                matched = re.match(time_format, i)
                if not matched:
                    raise ValueError('The time: ({}) input is incorrect'.format(i))
        else:
            raise ValueError('Start time or end time is null. Please enter again!')

        # Check uut_type & serial_number & area & machine
        if not check_data['uuttype'] and not check_data['sernum'] and \
                not check_data['area'] and not check_data['machine']:
            raise ValueError('uuttype & sernum & area & machine cannot be empty. Please enter again!')

    def start_crawl(self, first_request_data={}, download_file_list=[]):
        """
        Start the CCC crawler
        :param dict first_request_data: Fill in the first request data for spider
        :param list download_file_list: Fill in the specified file type to download
        :return:
        """
        self.input_info_check(first_request_data, download_file_list)
        params = {
            'test': '',
            'dataset': 'test_results',
            'database': None,
            'start': 0,
            'limit': '5000',
            'user': '',
            'attribute': '',
            'fttd': 0,
            'lttd': 0,
            'ftta': 0,
            'passedsampling': 0,
        }
        params.update(first_request_data)

        all_data = self.get_all_test_data(data=params)
        if not all_data or not all_data['results']:
            raise ValueError('No data was found, Please check that the information you entered is correct!')
        print('Crawling all test data is completed, test records count: {}'.format(len(all_data['results'])))

        self.download_results = []
        threads = []
        print('Start multi-threading to download the measurement file')
        for each_data in all_data['results']:
            t = threading.Thread(target=self.get_measurement_log_file, args=(each_data, download_file_list))
            t.daemon = True
            threads.append(t)

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()
        print('All the measurement files have been downloaded, download count: {}'.format(len(self.download_results)))


if __name__ == '__main__':
    spider = CCCSpider(login_account=('enter_your_cec_username', 'enter_your_cec_password'), thread_pool_max=10)
    spider.login_ccc(automatic_login=False, authentication_code='enter_your_pass_code')
    request_data = {
        'sernum': 'FOC24474C35',
        'uuttype': '',
        'area': '',
        'machine': '',
        'location': '',
        'passfail': 'A,F,P',
        'start_time': '2020-12-01 08:00:00',
        'end_time': '2020-12-30 20:00:00',
    }
    download_file = [
        {'limit_name': 'sequence_log', 'test_step_id': ''},
        {'limit_name': 'UUT_buffer', 'test_step_id': ''},
        # {'limit_name': 'UCLIM', 'test_step_id': 'UPX0 Bullet Test'},
        # {'limit_name': 'UCLIM', 'test_step_id': 'UPX1 Bullet Test'},
    ]
    spider.start_crawl(first_request_data=request_data, download_file_list=download_file)
