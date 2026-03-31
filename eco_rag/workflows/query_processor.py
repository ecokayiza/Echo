class QueryProcessor:
    """
    Routes and rewrites user queries before retrieval.
    """

    def prepare_query(self, user_query: str) -> str:
        return user_query.strip()
