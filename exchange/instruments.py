class InstrumentService:
    def __init__(self, client):
        self.client = client

    def get_swap_spec(self, inst_id: str):
        res = self.client.market.get_instruments(
            instType="SWAP",
            instId=inst_id
        )
        data = res["data"][0]
        return {
            "ctVal": float(data["ctVal"]),
            "lotSz": float(data["lotSz"]),
            "minSz": float(data["minSz"]),
            "tickSz": float(data["tickSz"]),
        }
