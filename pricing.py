#!/usr/bin/env python3

import requests
from pprint import pprint

class Pricing:
    costs = {}

    def __init__(self, region):
        data = requests.get('https://ec2.shop?region={}'.format(region), headers={'accept':'json'}).json()
        for i in data['Prices']:
            self.costs[i['InstanceType']] = i['Cost']
        return
    
    def get(self, instance_type):
        return self.costs[instance_type]