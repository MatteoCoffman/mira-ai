import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import { Construct } from "constructs";
import * as path from "path";

export interface MiraStackProps extends cdk.StackProps {
  /** Table name prefix, e.g. "mira" → mira-tenants */
  tablePrefix: string;
  openaiApiKey?: string;
  langchainApiKey?: string;
  langchainProject?: string;
  langchainTracingV2?: string;
  twilioAccountSid?: string;
  twilioAuthToken?: string;
  twilioPhoneNumber?: string;
  miraOwnerSmsPhone?: string;
}

export class MiraStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: MiraStackProps) {
    super(scope, id, props);

    const prefix = props.tablePrefix;
    const billing = dynamodb.BillingMode.PAY_PER_REQUEST;
    const removalPolicy = cdk.RemovalPolicy.RETAIN;

    const tenants = new dynamodb.Table(this, "TenantsTable", {
      tableName: `${prefix}-tenants`,
      partitionKey: { name: "tenant_id", type: dynamodb.AttributeType.STRING },
      billingMode: billing,
      removalPolicy,
    });

    const sessions = new dynamodb.Table(this, "SessionsTable", {
      tableName: `${prefix}-sessions`,
      partitionKey: { name: "session_id", type: dynamodb.AttributeType.STRING },
      billingMode: billing,
      removalPolicy,
    });

    const leads = new dynamodb.Table(this, "LeadsTable", {
      tableName: `${prefix}-leads`,
      partitionKey: { name: "session_id", type: dynamodb.AttributeType.STRING },
      billingMode: billing,
      removalPolicy,
    });

    const notifications = new dynamodb.Table(this, "NotificationsTable", {
      tableName: `${prefix}-notifications`,
      partitionKey: {
        name: "notification_id",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: billing,
      removalPolicy,
    });
    notifications.addGlobalSecondaryIndex({
      indexName: "session-index",
      partitionKey: { name: "session_id", type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    const toolCalls = new dynamodb.Table(this, "ToolCallsTable", {
      tableName: `${prefix}-tool-calls`,
      partitionKey: { name: "session_id", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "sk", type: dynamodb.AttributeType.STRING },
      billingMode: billing,
      removalPolicy,
    });

    const callRecords = new dynamodb.Table(this, "CallRecordsTable", {
      tableName: `${prefix}-call-records`,
      partitionKey: { name: "call_id", type: dynamodb.AttributeType.STRING },
      billingMode: billing,
      removalPolicy,
    });
    callRecords.addGlobalSecondaryIndex({
      indexName: "tenant-index",
      partitionKey: { name: "tenant_id", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "ended_at", type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    const apiSecret = new secretsmanager.Secret(this, "ApiSecret", {
      secretName: `${prefix}/api`,
      description: "Mira API credentials (OpenAI, Twilio, LangSmith)",
      secretObjectValue: {
        OPENAI_API_KEY: cdk.SecretValue.unsafePlainText(props.openaiApiKey ?? ""),
        LANGCHAIN_API_KEY: cdk.SecretValue.unsafePlainText(props.langchainApiKey ?? ""),
        TWILIO_ACCOUNT_SID: cdk.SecretValue.unsafePlainText(props.twilioAccountSid ?? ""),
        TWILIO_AUTH_TOKEN: cdk.SecretValue.unsafePlainText(props.twilioAuthToken ?? ""),
        TWILIO_PHONE_NUMBER: cdk.SecretValue.unsafePlainText(props.twilioPhoneNumber ?? ""),
        MIRA_OWNER_SMS_PHONE: cdk.SecretValue.unsafePlainText(props.miraOwnerSmsPhone ?? ""),
      },
    });

    const repoRoot = path.join(process.cwd(), "..");
    const bundleDir = path.join(repoRoot, "lambda_bundle");

    const apiFunction = new lambda.Function(this, "ApiFunction", {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: "api.lambda_handler.handler",
      code: lambda.Code.fromAsset(bundleDir),
      timeout: cdk.Duration.minutes(5),
      memorySize: 1024,
      environment: {
        MIRA_DB_BACKEND: "dynamodb",
        MIRA_TABLE_PREFIX: prefix,
        MIRA_SECRETS_ARN: apiSecret.secretArn,
        MIRA_VALIDATE_TWILIO_SIGNATURE: "true",
        LANGCHAIN_PROJECT: props.langchainProject ?? "mira-ai",
        LANGCHAIN_TRACING_V2: props.langchainTracingV2 ?? "true",
      },
    });

    apiSecret.grantRead(apiFunction);

    const tables = [tenants, sessions, leads, notifications, toolCalls, callRecords];
    for (const table of tables) {
      table.grantReadWriteData(apiFunction);
    }

    const functionUrl = apiFunction.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
    });

    new cdk.CfnOutput(this, "TablePrefix", { value: prefix });
    new cdk.CfnOutput(this, "TenantsTableName", { value: tenants.tableName });
    new cdk.CfnOutput(this, "SessionsTableName", { value: sessions.tableName });
    new cdk.CfnOutput(this, "LeadsTableName", { value: leads.tableName });
    new cdk.CfnOutput(this, "NotificationsTableName", {
      value: notifications.tableName,
    });
    new cdk.CfnOutput(this, "ToolCallsTableName", { value: toolCalls.tableName });
    new cdk.CfnOutput(this, "CallRecordsTableName", {
      value: callRecords.tableName,
    });
    new cdk.CfnOutput(this, "ApiSecretArn", {
      value: apiSecret.secretArn,
      description: "Secrets Manager JSON with OpenAI/Twilio/LangSmith keys",
    });
    new cdk.CfnOutput(this, "ApiFunctionUrl", {
      value: functionUrl.url,
      description: "Set Twilio webhooks to {url}twilio/voice/incoming and .../status",
    });
  }
}
