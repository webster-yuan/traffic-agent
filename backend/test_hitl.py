import asyncio, json
import httpx

async def stream_until_hitl(client):
    """Stream SSE events until waiting_for_approval or complete."""
    async with client.stream(
        'POST', 'http://127.0.0.1:8000/api/v1/traffic/generate/stream',
        json={'industry': 'ride_hailing', 'count': 2, 'stage': 'standard'}
    ) as resp:
        print(f'Stream Status: {resp.status_code}')
        buffer = ''
        events_seen = []
        async for chunk in resp.aiter_bytes():
            buffer += chunk.decode()
            while '\n\n' in buffer:
                event_str, buffer = buffer.split('\n\n', 1)
                lines = event_str.strip().split('\n')
                event_type = ''
                data = ''
                for line in lines:
                    if line.startswith('event:'):
                        event_type = line[6:].strip()
                    elif line.startswith('data:'):
                        data = line[5:].strip()
                events_seen.append(event_type)
                if event_type == 'waiting_for_approval':
                    parsed = json.loads(data)
                    return 'hitl', parsed, events_seen
                elif event_type == 'error':
                    return 'error', data, events_seen
                elif event_type == 'complete':
                    return 'complete', None, events_seen
        return 'stream_ended', None, events_seen


async def test_hitl_approve():
    """Test full HITL flow: stream → approve → complete."""
    print('\n=== Test: HITL Stream + Approve ===')
    async with httpx.AsyncClient(timeout=180) as client:
        status, data, events = await stream_until_hitl(client)
        if status != 'hitl':
            print(f'FAIL: Expected hitl, got {status}')
            return False
        
        session_id = data['session_id']
        print(f'HITL received: session={session_id}, records={data["record_count"]}, score={data["quality_score"]}')
        
        # Approve
        print(f'Resuming with approve...')
        resp = await client.post(
            f'http://127.0.0.1:8000/api/v1/traffic/resume/{session_id}',
            json={'action': 'approve', 'hint': ''}
        )
        result = resp.json()
        print(f'Resume result: {result}')
        if result.get('success'):
            print(f'PASS: Approved, download={result.get("download_url")}')
            return True
        else:
            print(f'FAIL: {result}')
            return False


async def test_hitl_reject():
    """Test full HITL flow: stream → reject → re-approve → complete."""
    print('\n=== Test: HITL Stream + Reject + Re-approve ===')
    async with httpx.AsyncClient(timeout=300) as client:
        status, data, events = await stream_until_hitl(client)
        if status != 'hitl':
            print(f'FAIL: Expected hitl, got {status}')
            return False
        
        session_id = data['session_id']
        print(f'HITL received: session={session_id}')
        
        # Reject with hint
        print(f'Resuming with reject...')
        resp = await client.post(
            f'http://127.0.0.1:8000/api/v1/traffic/resume/{session_id}',
            json={'action': 'reject', 'hint': 'Add more anomaly records'}
        )
        result = resp.json()
        print(f'Reject result: {result}')
        
        # May need re-approval after regenerate
        if result.get('status') == 'pending_approval':
            print('Re-approval needed after regenerate')
            resp2 = await client.post(
                f'http://127.0.0.1:8000/api/v1/traffic/resume/{session_id}',
                json={'action': 'approve', 'hint': ''}
            )
            result = resp2.json()
            print(f'Re-approve result: {result}')
        
        if result.get('success'):
            print(f'PASS: Rejected → regenerated → approved')
            return True
        else:
            print(f'Note: {result.get("message", result)}')
            return False


print('=' * 60)
print('HITL Full-Chain Test')
print('=' * 60)

result1 = asyncio.run(test_hitl_approve())
result2 = asyncio.run(test_hitl_reject())

print('\n' + '=' * 60)
print(f'Approve test: {"PASSED" if result1 else "FAILED"}')
print(f'Reject test: {"PASSED" if result2 else "FAILED"}')
