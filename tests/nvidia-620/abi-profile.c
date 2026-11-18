/* Independent public-header oracle; no driver ioctls or GPU work. */
#include <stddef.h>
#include <stdio.h>
#include <nvos.h>

#define OFFSET(type, member, expected) \
    _Static_assert(offsetof(type, member) == expected, #type "." #member)

_Static_assert(sizeof(NV_CHANNEL_GROUP_ALLOCATION_PARAMETERS) == 32, "TSG size");
OFFSET(NV_CHANNEL_GROUP_ALLOCATION_PARAMETERS, hObjectError, 0);
OFFSET(NV_CHANNEL_GROUP_ALLOCATION_PARAMETERS, hObjectEccError, 4);
OFFSET(NV_CHANNEL_GROUP_ALLOCATION_PARAMETERS, hVASpace, 8);
OFFSET(NV_CHANNEL_GROUP_ALLOCATION_PARAMETERS, engineType, 12);
OFFSET(NV_CHANNEL_GROUP_ALLOCATION_PARAMETERS, bIsCallingContextVgpuPlugin, 16);
OFFSET(NV_CHANNEL_GROUP_ALLOCATION_PARAMETERS, reserved, 20);
OFFSET(NV_CHANNEL_GROUP_ALLOCATION_PARAMETERS, reserved2, 24);
OFFSET(NV_CHANNEL_GROUP_ALLOCATION_PARAMETERS, internalFlags, 28);
_Static_assert(sizeof(NV_CTXSHARE_ALLOCATION_PARAMETERS) == 16, "context size");
OFFSET(NV_CTXSHARE_ALLOCATION_PARAMETERS, hVASpace, 0);
OFFSET(NV_CTXSHARE_ALLOCATION_PARAMETERS, flags, 4);
OFFSET(NV_CTXSHARE_ALLOCATION_PARAMETERS, subctxId, 8);
OFFSET(NV_CTXSHARE_ALLOCATION_PARAMETERS, reserved, 12);

int main(void)
{
    puts("PASS: NVIDIA 620.70.06 TSG/context-share public C layouts");
    return 0;
}
