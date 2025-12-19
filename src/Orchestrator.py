


############################################
# !Core
# Handle Query Routing and Rewriting, also makes retreial plans
# INPUT:
#   - User Query
#   - Iteration from Adapter           (Retrival Evaluation)          
#   - Iteration from ContextManager    (Generation Evaluation)
#   (rewrite is not always needed)
# OUTPUT:
#   - Directly to Model                (No retrival needed)
#   - To Retriever with retreival plan 
############################################