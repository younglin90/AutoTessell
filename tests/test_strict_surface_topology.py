from __future__ import annotations
import numpy as np
from core.evaluator.strict_surface_topology import audit_strict_surface_topology

def _tetra():
    return np.asarray(((0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.))), np.asarray(((0,2,1),(0,1,3),(1,2,3),(2,0,3)))

def test_closed_surface_is_strict():
    points,faces=_tetra()
    audit=audit_strict_surface_topology(points,faces)
    assert audit.valid
    assert audit.n_duplicate_faces==0
    assert audit.n_nonmanifold_edges==0
    assert audit.n_open_edges==0
    assert audit.n_inverted_faces==0
    assert len(audit.artifact_sha256)==64

def test_surface_debt_is_not_hidden():
    points,faces=_tetra()
    audit=audit_strict_surface_topology(points,np.vstack((faces,faces[0])))
    assert not audit.valid
    assert audit.n_duplicate_faces==1
