import random
def get_random_tap(x1,y1,x2,y2): #for click
    x1_random = random.randint(x1,x2) #randomization 
    y1_random = random.randint(y1,y2)

    return x1_random,y1_random

def get_random_swipe(x1,y1,x2,y2): #for swipe, plus minus x pixels
    x = 20
    x1 = random.randint(x1-x,x1+x)
    x2 = random.randint(x2-x,x2+x)
    y1 = random.randint(y1-x,y1+x)
    y2 = random.randint(y2-x,y2+x)

    return x1,y1,x2,y2