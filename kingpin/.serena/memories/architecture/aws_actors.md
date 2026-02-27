# AWS Actor Details

## AWSBaseActor (actors/aws/base.py)
- Creates boto3 clients: iam_conn (always), ecs/cfn/sqs/s3_conn (if region set)
- `api_call(func, *args, **kwargs)` -- runs sync boto3 in ThreadPoolExecutor(10)
- `api_call_with_queueing(func, queue_name)` -- serialized queue with backoff
- `_parse_json(file_path)` -- loads JSON with token replacement for policy files
- Credentials: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN from env
- Retry: AWS_MAX_ATTEMPTS=10, AWS_RETRY_MODE="standard" (configurable via env)

## ApiCallQueue (actors/aws/api_call_queue.py)
- Serializes calls per queue_name (global NAMED_API_CALL_QUEUES dict)
- Exponential backoff on Throttling: 0.25s min, 30s max
- `_decrease_delay()` halves delay; `_increase_delay()` doubles it
- Consumer runs in background via asyncio.ensure_future
- Result passing via per-call asyncio.Queue(maxsize=1)

## CloudFormation actors (actors/aws/cloudformation.py, 1348 lines)
### CloudFormationBaseActor
- Template from file path or S3 URL (s3://bucket/key regex)
- `_validate_template()` via CFN API
- `_create_parameters()` merges file params + noecho handling (UsePreviousValue)
- `_wait_until_state()` polls describe_stacks with configurable sleep, streams events
- State constants: COMPLETE, DELETED, IN_PROGRESS, FAILED (lists of CFN status strings)

### Stack (most complex actor)
- Hash optimization: MD5 of template body stored as stack output (KINGPIN_CFN_HASH_OUTPUT_KEY)
- Change set workflow: create -> wait ready -> print changes -> execute -> wait complete
- `_diff_params_safely()` hides NoEcho param values in diffs
- Termination protection management
- Role ARN support (KINGPIN_CFN_DEFAULT_ROLE_ARN env var)

## IAM actors (actors/aws/iam.py, 1114 lines)
### IAMBaseActor -- generalized entity management
- Maps generic names to boto3 methods: create_entity, delete_entity, get_entity, etc.
- `entity_name` property drives API call kwargs (UserName, GroupName, RoleName, etc.)
- Inline policy management: parse JSON files -> compare with AWS -> push/delete diffs
- Uses asyncio.TaskGroup for parallel policy operations

### Subclasses just bind method references:
- User: + group membership management (_ensure_groups)
- Group: + force delete with member purge (_purge_group_users)
- Role: + assume role policy document management
- InstanceProfile: + role assignment (add/remove)

## S3 Bucket (actors/aws/s3.py, 1187 lines)
- Extends EnsurableAWSBaseActor (both AWS + Ensurable)
- Schema validators: LifecycleConfig, LoggingConfig, TaggingConfig, PublicAccessBlockConfig, NotificationConfiguration
- `_snake_to_camel()` via inflection library for AWS API compatibility
- `_precache()` checks bucket existence via list_buckets
- Won't delete non-empty buckets (safety check)
- Each managed aspect has full get/set/compare cycle

## AWS Settings (actors/aws/settings.py)
- KINGPIN_CFN_HASH_OUTPUT_KEY (default "KingpinCfnHash", "" to disable)
- KINGPIN_CFN_DEFAULT_ROLE_ARN (default None)
