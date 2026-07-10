#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import * as dotenv from "dotenv";
import * as path from "path";
import { MiraStack } from "../lib/mira-stack";

dotenv.config({ path: path.join(__dirname, "../../.env") });

const app = new cdk.App();

const tablePrefix = app.node.tryGetContext("tablePrefix") ?? "mira";

new MiraStack(app, "MiraStack", {
  tablePrefix,
  openaiApiKey: process.env.OPENAI_API_KEY,
  langchainApiKey: process.env.LANGCHAIN_API_KEY,
  langchainProject: process.env.LANGCHAIN_PROJECT,
  langchainTracingV2: process.env.LANGCHAIN_TRACING_V2,
  twilioAccountSid: process.env.TWILIO_ACCOUNT_SID,
  twilioAuthToken: process.env.TWILIO_AUTH_TOKEN,
  twilioPhoneNumber: process.env.TWILIO_PHONE_NUMBER,
  miraOwnerSmsPhone: process.env.MIRA_OWNER_SMS_PHONE,
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? "us-east-1",
  },
});
