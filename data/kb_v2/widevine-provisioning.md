# Widevine provisioning and license errors

## Provisioning
A device needs a provisioning certificate before it can request licenses. `MediaDrm` signals a
missing one with `NotProvisionedException`; Media3 runs provisioning for you.

## License failures
Log the license request and the server's response status: a policy refusal, an expired key, and a
network error need different fixes.
