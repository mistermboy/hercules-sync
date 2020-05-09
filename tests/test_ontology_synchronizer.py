import pytest

import ontospy

from unittest import mock

from hercules_sync.synchronization import OntologySynchronizer, GraphDiffSyncAlgorithm, \
                                          NaiveSyncAlgorithm, AdditionOperation, RemovalOperation
from hercules_sync.synchronization.ontology_synchronizer import _filter_invalid_ops
from hercules_sync.triplestore import LiteralElement, URIElement
from hercules_sync.util.uri_constants import OWL_BASE

from .common import load_gitfile_from

SOURCE_FILE = 'source_props.ttl'
TARGET_FILE = 'target_props.ttl'

SOURCE_FILE_RANGE = 'source_props_range.ttl'
TARGET_FILE_RANGE = 'target_props_range.ttl'

EX_PREFIX = 'http://www.semanticweb.org/spitxa/ontologies/2020/1/asio-human-resource#'

@pytest.fixture(scope='module')
def input():
    return load_gitfile_from(SOURCE_FILE, TARGET_FILE)

@pytest.fixture(scope='module')
def input_range():
    return load_gitfile_from(SOURCE_FILE_RANGE, TARGET_FILE_RANGE)

@pytest.fixture
def mock_synchronizer():
    with mock.patch.object(OntologySynchronizer, '__init__', lambda slf, algorithm: None):
        synchronizer = OntologySynchronizer(None)
        synchronizer._algorithm = mock.MagicMock()
        synchronizer._annotate_triples = mock.MagicMock()
        yield synchronizer

@pytest.fixture
def operations_fixture(input):
    algorithm = GraphDiffSyncAlgorithm()
    return algorithm.do_algorithm(input)

def test_init():
    synchronizer = OntologySynchronizer(None)
    assert isinstance(synchronizer._algorithm, NaiveSyncAlgorithm)

    synchronizer = OntologySynchronizer(GraphDiffSyncAlgorithm())
    assert isinstance(synchronizer._algorithm, GraphDiffSyncAlgorithm)

def test_filter_invalid_ops():
    ops = [AdditionOperation(LiteralElement("a"), URIElement("https://example.org"), None),
           RemovalOperation(LiteralElement("b"), None, LiteralElement("c")),
           AdditionOperation(LiteralElement("a"), URIElement("https://example.org"), LiteralElement(2))]
    filtered_ops = _filter_invalid_ops(ops)
    assert len(filtered_ops) == 1
    assert filtered_ops[0] == ops[2]

def test_synchronize(mock_synchronizer):
    mock_synchronizer.synchronize(None)
    mock_synchronizer._algorithm.do_algorithm.assert_has_calls([mock.call(None)])

def test_etype_annotation(input):
    algorithm = GraphDiffSyncAlgorithm()
    ops = algorithm.do_algorithm(input)
    # check that original operations have default annotations
    for op in ops:
        for element in op._triple_info:
            if element.is_uri:
                assert element.etype == 'item'

    synchronizer = OntologySynchronizer(algorithm)
    synchronizer._annotate_triples(ops, input)
    # check that now the subjects of this ontology are classified as properties
    for op in ops:
        triple_info = op._triple_info
        assert triple_info.subject.etype == 'property'

def test_prop_range_annotation(input_range):
    algorithm = GraphDiffSyncAlgorithm()
    ops = algorithm.do_algorithm(input_range)
    synchronizer = OntologySynchronizer(algorithm)
    synchronizer._annotate_triples(ops, input_range)
    expected = {
        f"{EX_PREFIX}authors": 'wikibase-item',
        f"{EX_PREFIX}fund": 'wikibase-item',
        f"{EX_PREFIX}projectEndDate": 'time',
        f"{EX_PREFIX}projectKeyword": 'string',
        f"{EX_PREFIX}projectFund": 'quantity',
        f"{OWL_BASE}subPropertyOf": None # no range and datatype is not inferred
    }
    for op in ops:
        for el in op._triple_info:
            if el.uri in expected:
                assert el.wdi_proptype == expected[el.uri]
