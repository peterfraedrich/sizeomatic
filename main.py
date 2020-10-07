#!/usr/bin/env python3

import boto3
import fire
import os
import peewee
from pprint import pprint
import logging
from pricing import Pricing

DB = peewee.SqliteDatabase(None)

class SizeOMatic:
    region = 'us-east-1'

    def __init__(self, region='us-east-1'):
        self.region = region
        os.environ['AWS_DEFAULT_REGION'] = region
        DB.init('sizeomatic.db')
        DB.connect()

    def find(self):
        metrics = {
            'asg_count' : 0,
            'asg_opt' : 0,
            'ec2_count' : 0,
            'ec2_opt' : 0
        }
        DB.drop_tables([instance, ec2options, asg, asgoptions])
        DB.create_tables([instance, ec2options, asg, asgoptions])
        aws = boto3.client('compute-optimizer')
        print("Getting ASG recommendations...")
        asg_recs = aws.get_auto_scaling_group_recommendations(filters=[{'name':'Finding','values':['NotOptimized']}])['autoScalingGroupRecommendations']
        print("Getting EC2 recommendations...")
        ec2_recs = aws.get_ec2_instance_recommendations(filters=[{'name':'Finding', 'values':['Overprovisioned']},{'name':'RecommendationSourceType','values':['Ec2Instance']}])['instanceRecommendations']
        aws_prices = Pricing(self.region)
        print('Saving data to local db...')
        for i in asg_recs:
            base_cost = aws_prices.get(i['currentConfiguration']['instanceType'])*float(i['currentConfiguration']['maxSize'])
            new = asg.create(
                account=i['accountId'],
                arn=i['autoScalingGroupArn'],
                name=i['autoScalingGroupName'],
                desired_cap=i['currentConfiguration']['desiredCapacity'],
                instance_type=i['currentConfiguration']['instanceType'],
                max_size=i['currentConfiguration']['maxSize'],
                min_size=i['currentConfiguration']['minSize'],
                hourly_price=base_cost,
                monthly_price=base_cost * 24.0 * 30.0,
            )
            new.save()
            metrics['asg_count'] = metrics['asg_count'] + 1
            for o in i['recommendationOptions']:
                recc_cost = aws_prices.get(o['configuration']['instanceType'])*float(o['configuration']['maxSize'])
                asg_option = asgoptions.create(
                    asg_id=new.id,
                    desired_cap=o['configuration']['desiredCapacity'],
                    instance_type=o['configuration']['instanceType'],
                    max_size=o['configuration']['maxSize'],
                    min_size=o['configuration']['minSize'],
                    risk=o['performanceRisk'],
                    cpu_max=o['projectedUtilizationMetrics'][0]['value'],
                    rank=o['rank'],
                    hourly_delta=base_cost-recc_cost,
                    monthly_delta=(base_cost * 24.0 * 30.0) - (recc_cost*24.0*30.0)
                )
                asg_option.save()
                metrics['asg_opt'] = metrics['asg_opt'] + 1
        for i in ec2_recs:
            base_cost = aws_prices.get(i['currentInstanceType'])
            new = instance.create(
                name=i['instanceName'],
                account=i['accountId'],
                arn=i['instanceArn'],
                current_type=i['currentInstanceType'],
                cpu_max=i['utilizationMetrics'][0]['value'],
                hourly_price=base_cost,
                monthly_price=base_cost*24.0*30.0,
            )
            new.save()
            metrics['ec2_count'] = metrics['ec2_count'] +  1
            for o in i['recommendationOptions']:
                recc_cost = aws_prices.get(o['instanceType'])
                opt = ec2options.create(
                    ec2_id=new.id,
                    instance_type=o['instanceType'],
                    risk=o['performanceRisk'],
                    cpu_max=o['projectedUtilizationMetrics'][0]['value'],
                    rank=o['rank'],
                    hourly_delta=base_cost-recc_cost,
                    monthly_delta=(base_cost*24.0*30.0)-(recc_cost*24.0*30.0)
                )
                opt.save()
                metrics['ec2_opt'] = metrics['ec2_opt'] + 1
        print('Finished processing recommendations.')
        print('{:5}|{:5}|{:5}'.format('TYPE', 'NUM', 'RECS'))
        print('-----|-----|-----')
        print('{:5}|{:5}|{:5}'.format('ASG', metrics['asg_count'], metrics['asg_opt']))
        print('{:5}|{:5}|{:5}'.format('EC2', metrics['ec2_count'], metrics['ec2_opt']))
        return

    def tag(self, dry=True):
        boto3.client('ec2').create_tags(DryRun=dry, Resources=[x.arn.split('/')[1] for x in instance.select()], Tags=[{'Key':'sizeomatic_status', 'Value':'resize_pending'}])
        return

    def untag(self, dry=True):
        boto3.client('ec2').delete_tags(DryRun=dry, Resources=[x.arn.split('/')[1] for x in instance.select()], Tags=[{'Key':'sizeomatic_status'}])
        return

class instance(peewee.Model):
    name = peewee.CharField()
    account = peewee.IntegerField()
    arn = peewee.CharField()
    current_type = peewee.CharField()
    cpu_max = peewee.IntegerField()
    hourly_price = peewee.FloatField()
    monthly_price = peewee.FloatField()
    class Meta:
        database = DB

class ec2options(peewee.Model):
    ec2_id = peewee.ForeignKeyField(instance)
    instance_type = peewee.CharField()
    risk = peewee.FloatField()
    cpu_max = peewee.FloatField()
    rank = peewee.IntegerField()
    hourly_delta = peewee.FloatField()
    monthly_delta = peewee.FloatField()
    class Meta:
        database = DB

class asg(peewee.Model):
    account = peewee.IntegerField()
    arn = peewee.CharField()
    name = peewee.CharField()
    desired_cap = peewee.IntegerField()
    instance_type = peewee.CharField()
    max_size = peewee.IntegerField()
    min_size = peewee.IntegerField()
    hourly_price = peewee.FloatField()
    monthly_price = peewee.FloatField()
    class Meta:
        database = DB

class asgoptions(peewee.Model):
    asg_id = peewee.ForeignKeyField(asg)
    desired_cap = peewee.IntegerField()
    instance_type = peewee.CharField()
    max_size = peewee.IntegerField()
    min_size = peewee.IntegerField()
    risk = peewee.FloatField()
    cpu_max = peewee.FloatField()
    rank = peewee.IntegerField()
    hourly_delta = peewee.FloatField()
    monthly_delta = peewee.FloatField()
    class Meta:
        database = DB

if __name__ == '__main__':
    fire.Fire(SizeOMatic)