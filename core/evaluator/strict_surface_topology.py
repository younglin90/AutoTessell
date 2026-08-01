"""Independent strict topology audit for written or in-memory surface products."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
import numpy as np

_CONTRACT="autotessell/strict-surface-topology/v1"

@dataclass(frozen=True, slots=True)
class StrictSurfaceTopologyAudit:
    status: str
    valid: bool
    artifact_sha256: str | None
    n_vertices: int
    n_faces: int
    n_duplicate_faces: int
    n_nonmanifold_edges: int
    n_open_edges: int
    n_degenerate_faces: int
    n_inverted_faces: int
    boundary_surface_valid: bool
    malformed_reason: str | None = None
    contract: str = _CONTRACT
    def as_dict(self) -> dict[str, object]:
        return {
            "kind":"surface","status":self.status,"valid":self.valid,
            "artifact_sha256":self.artifact_sha256,
            "n_vertices":self.n_vertices,"n_faces":self.n_faces,
            "n_duplicate_faces":self.n_duplicate_faces,
            "n_nonmanifold_edges":self.n_nonmanifold_edges,
            "n_open_edges":self.n_open_edges,
            "n_degenerate_faces":self.n_degenerate_faces,
            "n_inverted_faces":self.n_inverted_faces,
            "surface_topology_valid":self.valid,
            "boundary_surface_valid":self.boundary_surface_valid,
            "malformed_reason":self.malformed_reason,"contract":self.contract,
        }

def _digest(points: np.ndarray, faces: np.ndarray) -> str:
    h=hashlib.sha256()
    for array in (points,faces):
        a=np.ascontiguousarray(array)
        h.update(json.dumps({"dtype":a.dtype.str,"shape":tuple(a.shape)},sort_keys=True).encode())
        h.update(a.tobytes())
    return h.hexdigest()

def audit_strict_surface_topology(vertices: object, faces: object) -> StrictSurfaceTopologyAudit:
    try:
        points=np.asarray(vertices,dtype=np.float64)
        surface=np.asarray(faces,dtype=np.int64)
    except (TypeError,ValueError) as exc:
        return StrictSurfaceTopologyAudit("malformed",False,None,0,0,0,0,0,0,0,False,type(exc).__name__)
    if points.ndim!=2 or points.shape[1:]!=(3,) or not len(points) or not np.isfinite(points).all():
        return StrictSurfaceTopologyAudit("malformed",False,None,len(points) if points.ndim else 0,0,0,0,0,0,0,False,"vertices_invalid")
    if surface.ndim!=2 or surface.shape[1:]!=(3,) or not len(surface):
        return StrictSurfaceTopologyAudit("malformed",False,None,len(points),0,0,0,0,0,0,False,"faces_invalid")
    if np.any(surface<0) or np.any(surface>=len(points)):
        return StrictSurfaceTopologyAudit("malformed",False,None,len(points),len(surface),0,0,0,0,0,False,"face_incidence_invalid")
    canonical=np.sort(surface,axis=1)
    _,counts=np.unique(canonical,axis=0,return_counts=True)
    duplicates=int(np.maximum(counts-1,0).sum())
    edge_records: dict[tuple[int,int],list[tuple[int,int]]]={}
    degenerate=0
    for face_index,face in enumerate(surface):
        a,b,c=(points[int(index)] for index in face)
        cross=np.cross(b-a,c-a)
        if float(np.linalg.norm(cross))<=1e-14:
            degenerate+=1
        for local,(first,second) in enumerate(((int(face[0]),int(face[1])),(int(face[1]),int(face[2])),(int(face[2]),int(face[0])))):
            key=(min(first,second),max(first,second))
            direction=1 if (first,second)==key else -1
            edge_records.setdefault(key,[]).append((face_index,direction))
    nonmanifold=sum(1 for owners in edge_records.values() if len(owners)>2)
    open_edges=sum(1 for owners in edge_records.values() if len(owners)==1)
    inverted=sum(1 for owners in edge_records.values() if len(owners)==2 and owners[0][1]==owners[1][1])
    valid=duplicates==0 and nonmanifold==0 and open_edges==0 and degenerate==0 and inverted==0
    return StrictSurfaceTopologyAudit(
        "measured",valid,_digest(points,surface),len(points),len(surface),
        duplicates,nonmanifold,open_edges,degenerate,inverted,valid,
        None if valid else "strict_surface_topology_debt",
    )

__all__=["StrictSurfaceTopologyAudit","audit_strict_surface_topology"]
