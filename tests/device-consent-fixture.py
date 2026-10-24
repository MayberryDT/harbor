"""Explicit disposable-device consent for native E2E setup.
Failure cases for the new boundary: no target consent; forged signature; proof
reused for another root or binding; a foreign roster claiming a pinned endpoint;
a rejected multi-endpoint import leaving an immutable anchor behind.
"""
def consent(peer, person):
    request = 'fixture-consent-' + str(peer.mark())
    peer.send({'op':'device.consent','request':request,'key':person,'accept':True})
    result = peer.wait(lambda e:e.get('request') == request and e.get('event') in ('devices.consent','devices.error'),15)
    assert result['event'] == 'devices.consent', result
    return result['proof']
