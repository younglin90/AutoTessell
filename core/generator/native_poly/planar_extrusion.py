"""Structured polyhedral wedges for watertight planar extrusions."""
from __future__ import annotations

import numpy as np

from core.generator.native_tet.thin_extrusion import (
    ThinExtrusionMesh,
    _extrusion_axis,
)

def build_planar_extrusion_wedges(
    vertices: np.ndarray,
    faces: np.ndarray,
    *,
    target_cells: int,
    min_bbox_aspect: float = 5.0,
) -> ThinExtrusionMesh | None:
    points=np.asarray(vertices,dtype=np.float64)
    triangles=np.asarray(faces,dtype=np.int64)
    detected=_extrusion_axis(points,triangles,min_bbox_aspect=min_bbox_aspect)
    if detected is None:
        return None
    axis,lower_mask,upper_mask=detected
    lower_ids=np.unique(triangles[lower_mask].reshape(-1))
    upper_ids=np.unique(triangles[upper_mask].reshape(-1))
    if len(lower_ids)<3 or len(lower_ids)!=len(upper_ids):
        return None
    uv_axes=((axis+1)%3,(axis+2)%3)
    lower=float(points[:,axis].min()); upper=float(points[:,axis].max())
    scale=max(float(np.max(np.ptp(points,axis=0))),1.0)
    lower_proj=points[lower_ids][:,uv_axes]
    upper_proj=points[upper_ids][:,uv_axes]
    mapping={}
    for local,coord in enumerate(lower_proj):
        distances=np.linalg.norm(upper_proj-coord[None,:],axis=1)
        index=int(np.argmin(distances))
        if float(distances[index])>scale*1e-8 or int(upper_ids[index]) in mapping.values():
            return None
        mapping[int(lower_ids[local])]=int(upper_ids[index])
    lower_face_rows=triangles[lower_mask]
    if len(lower_face_rows)==0:
        return None
    n_cap=len(lower_ids)
    n_slabs=max(1,int(round(float(target_cells)/max(len(lower_face_rows),1))))
    output=np.empty(((n_slabs+1)*n_cap,3),dtype=np.float64)
    lower_points=points[lower_ids]
    upper_points=points[[mapping[int(index)] for index in lower_ids]]
    for layer in range(n_slabs+1):
        fraction=layer/n_slabs
        output[layer*n_cap:(layer+1)*n_cap]=lower_points*(1.0-fraction)+upper_points*fraction
    local={int(vertex):index for index,vertex in enumerate(lower_ids)}
    cells=[]
    for layer in range(n_slabs):
        for raw in lower_face_rows:
            ids=[local[int(value)] for value in raw]
            projected=lower_points[ids][:,uv_axes]
            first=projected[1]-projected[0]
            second=projected[2]-projected[0]
            signed=float(first[0]*second[1]-first[1]*second[0])
            a,b,c=ids
            if signed<0.0: b,c=c,b
            bottom=[layer*n_cap+i for i in (a,b,c)]
            top=[(layer+1)*n_cap+i for i in (a,b,c)]
            cells.append([
                [bottom[2],bottom[1],bottom[0]],
                [top[0],top[1],top[2]],
                [bottom[0],bottom[1],top[1],top[0]],
                [bottom[1],bottom[2],top[2],top[1]],
                [bottom[2],bottom[0],top[0],top[2]],
            ])
    return ThinExtrusionMesh(
        points=output,
        cell_faces=cells,
        extrusion_axis=axis,
        n_slabs=n_slabs,
        n_cap_triangles=len(lower_face_rows),
    )

__all__=["build_planar_extrusion_wedges"]
