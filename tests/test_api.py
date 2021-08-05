import httpcore



def test_request(httpbin):
    response = httpcore.request("GET", httpbin.url)
    assert response.status == 200
