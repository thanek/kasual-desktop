"""UPnP/DLNA ContentDirectory browsing."""

import dataclasses
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
from urllib.request import Request, urlopen

_CD_SERVICE = "ContentDirectory"

_BROWSE_SOAP = """\
<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:Browse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">
      <ObjectID>{object_id}</ObjectID>
      <BrowseFlag>BrowseDirectChildren</BrowseFlag>
      <Filter>*</Filter>
      <StartingIndex>0</StartingIndex>
      <RequestedCount>0</RequestedCount>
      <SortCriteria></SortCriteria>
    </u:Browse>
  </s:Body>
</s:Envelope>"""


@dataclasses.dataclass
class DlnaEntry:
    id: str
    title: str
    is_container: bool
    mime_type: str = ""
    resource_url: str = ""


def get_control_url(location: str) -> str | None:
    """Fetch device descriptor XML and return ContentDirectory control URL, or None."""
    try:
        with urlopen(location, timeout=5) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        ns = {"d": "urn:schemas-upnp-org:device-1-0"}
        for svc in root.findall(".//d:service", ns):
            stype = svc.findtext("d:serviceType", namespaces=ns) or ""
            if _CD_SERVICE in stype:
                ctrl = svc.findtext("d:controlURL", namespaces=ns) or ""
                return urljoin(location, ctrl)
    except Exception:
        pass
    return None


def browse(control_url: str, object_id: str = "0") -> list[DlnaEntry]:
    """Return direct children of a DLNA container."""
    body = _BROWSE_SOAP.format(object_id=object_id)
    req = Request(
        control_url,
        data=body.encode(),
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": '"urn:schemas-upnp-org:service:ContentDirectory:1#Browse"',
        },
    )
    try:
        with urlopen(req, timeout=10) as resp:
            data = resp.read()
    except Exception:
        return []

    try:
        envelope = ET.fromstring(data)
    except ET.ParseError:
        return []

    result_text = None
    for el in envelope.iter():
        if el.tag.endswith("}Result") or el.tag == "Result":
            result_text = el.text
            break
    if not result_text:
        return []

    try:
        didl = ET.fromstring(result_text)
    except ET.ParseError:
        return []

    ns = {
        "d": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    entries: list[DlnaEntry] = []

    for container in didl.findall("d:container", ns):
        eid = container.get("id", "")
        title = container.findtext("dc:title", namespaces=ns) or eid
        entries.append(DlnaEntry(id=eid, title=title, is_container=True))

    for item in didl.findall("d:item", ns):
        eid = item.get("id", "")
        title = item.findtext("dc:title", namespaces=ns) or eid
        res = item.find("d:res", ns)
        resource_url = (res.text or "").strip() if res is not None else ""
        proto = (res.get("protocolInfo", "") if res is not None else "").split(":")
        mime = proto[2] if len(proto) > 2 else ""
        entries.append(DlnaEntry(id=eid, title=title, is_container=False,
                                  mime_type=mime, resource_url=resource_url))

    return entries
