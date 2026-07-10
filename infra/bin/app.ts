#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { MiraStack } from "../lib/mira-stack";

const app = new cdk.App();

const tablePrefix = app.node.tryGetContext("tablePrefix") ?? "mira";

new MiraStack(app, "MiraStack", {
  tablePrefix,
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? "us-east-1",
  },
});
