/*
    This file is part of Orange.

    Orange is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    Orange is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with Orange; if not, write to the Free Software
    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

    Authors: Janez Demsar, Blaz Zupan, 1996--2002
    Contact: janez.demsar@fri.uni-lj.si
*/


#ifndef __DIST_CLUSTERING_HPP
#define __DIST_CLUSTERING_HPP

#include "induce.hpp"
#include "decomposition.hpp"
#include "exampleclustering.hpp"

#include "slist.hpp"
#include "pqueue_i.hpp"

class TDistProfitNode;
typedef TPriorityQueue<TDistProfitNode> TDistProfitQueue;

typedef slist<TDistProfitNode> TDistProfitNodeList;

class TDistClusterNode {
public:
  TDistClusterNode *nextNode, *prevNode;
  PDistribution distribution;
  TDistProfitNodeList mergeProfits;
  PExampleCluster cluster;
  float distributionQuality_N;

  TDistClusterNode(PDistribution distribution, const PExample &example, const float &quality, TDistClusterNode *prevNode=NULL);
  virtual ~TDistClusterNode(); // deletes the data (columns) and mergeProfits, but not mergeProfits (to avoid double delete, this is done by queue)
};


class TDistProfitNode {
public:
  TDistClusterNode *cluster1, *cluster2;
  float profit;

  TDistProfitNodeList *it1, *it2;
  int queueIndex;

  long randoff;

  TDistProfitNode(TDistClusterNode *c1, TDistClusterNode *c2, const float &prof, const int &qind, const long &roff);
  virtual ~TDistProfitNode();
  int compare(const TDistProfitNode &) const;
};


WRAPPER(MeasureAttribute)

class TDistributionAssessor : public TOrange {
public:
  __REGISTER_ABSTRACT_CLASS

  TDistributionAssessor();

  virtual void setDistribution(const TDiscDistribution &);
  virtual void setAverage(const float &avg);

  virtual float distributionQuality(TDistClusterNode &node) const=0;
  virtual float mergeProfit (const TDistClusterNode &, const TDistClusterNode &) const=0;
};

WRAPPER(DistributionAssessor)


class TStopDistributionClustering : public TOrange {
public:
  __REGISTER_ABSTRACT_CLASS
  virtual bool operator()(const float &baseQuality, const TDistProfitQueue &, const TDistClusterNode *clusters) const =0;
};

WRAPPER(StopDistributionClustering);




class T_ExampleDist {
public:
  PExample example;
  PDistribution distribution;

  T_ExampleDist(PExample anexample=PExample(), PDistribution distribution=PDistribution());
};

class TExampleDistVector : public TOrange {
public:
  __REGISTER_CLASS
  vector<T_ExampleDist> values;

  int traverse(visitproc visit, void *arg) const;
  int dropReferences();
};

WRAPPER(ExampleDistVector)


class TExampleDistConstructor : public TOrange {
public:
  __REGISTER_ABSTRACT_CLASS
  virtual PExampleDistVector operator()(PExampleGenerator, TVarList &, const int &weightID=0) =0;
};

WRAPPER(ExampleDistConstructor)


class TExampleDistBySorting : public TExampleDistConstructor {
public:
  __REGISTER_CLASS
  virtual PExampleDistVector operator()(PExampleGenerator, TVarList &, const int &weightID=0);
};




class TClustersFromDistributions : public TOrange {
public:
  __REGISTER_ABSTRACT_CLASS
  virtual PExampleClusters operator()(PExampleDistVector)=0;
};

WRAPPER(ClustersFromDistributions);


class TClustersFromDistributionsByAssessor : public TClustersFromDistributions {
public:
  __REGISTER_CLASS

  PDistributionAssessor distributionAssessor; //P column quality assessor
  PStopDistributionClustering stopCriterion; //P stop criterion
  float minProfitProportion; //P minimal merge profit

  TClustersFromDistributionsByAssessor(float mpp=0, PDistributionAssessor = PDistributionAssessor());

  virtual PExampleClusters operator()(PExampleDistVector);

protected:
  virtual void  preparePrivateVars(PExampleDistVector, TDistClusterNode *&clusters, TDistProfitQueue &, float &baseQuality, float &N, TSimpleRandomGenerator &);
  virtual void computeQualities(TDistClusterNode *&clusters, TDistProfitQueue &, float &baseQuality, float &N, TSimpleRandomGenerator &);
  void  mergeBestColumns(TDistClusterNode *&clusters, TDistProfitQueue &, float &baseQuality, float &N, TSimpleRandomGenerator &);
  
  TDistProfitNode *insertProfitQueueNode(TDistClusterNode *, TDistClusterNode *, float profit, long randoffset, TDistProfitQueue &);
};



class TFeatureByDistributions : public TFeatureInducer {
public:
  __REGISTER_CLASS

  PClustersFromDistributions clustersFromDistributions; //P clustering algorithm
  int completion; //P decides how to determine the class for points not covered by any cluster

  TFeatureByDistributions(PClustersFromDistributions = PClustersFromDistributions(), const int &completion = completion_bayes);
  PVariable operator()(PExampleGenerator gen, TVarList &boundSet, const string &name, float &quality, const int &weight=0);
};




/* Down there are only different distribution assessors and stop criterions */

class TDistributionAssessor_m : public TDistributionAssessor {
public:
  __REGISTER_CLASS

  float m; //P m for m-estimate

  TDistributionAssessor_m(const float &am=2.0);

  virtual void setDistribution(const TDiscDistribution &apbym);

  virtual float distributionQuality(TDistClusterNode &node) const;
  virtual float mergeProfit (const TDistClusterNode &, const TDistClusterNode &) const;

  float m_error(const TDiscDistribution &) const; 
  float m_error(const TDiscDistribution &, const TDiscDistribution &) const;

private:
  vector<float> p_by_m;
};


class TDistributionAssessor_Laplace : public TDistributionAssessor {
public:
  __REGISTER_CLASS

  virtual float distributionQuality(TDistClusterNode &node) const;
  virtual float mergeProfit (const TDistClusterNode &, const TDistClusterNode &) const;
};


class TDistributionAssessor_Relief : public TDistributionAssessor {
public:
  __REGISTER_CLASS

  virtual float distributionQuality(TDistClusterNode &node) const;
  virtual float mergeProfit (const TDistClusterNode &, const TDistClusterNode &) const;
};


class TDistributionAssessor_Kramer : public TDistributionAssessor {
public:
  __REGISTER_CLASS

  virtual float distributionQuality(TDistClusterNode &node) const;
  virtual float mergeProfit (const TDistClusterNode &, const TDistClusterNode &) const;
};


class TDistributionAssessor_Measure : public TDistributionAssessor  {
public:
  __REGISTER_CLASS

  PMeasureAttribute measure; //P attribute quality measure
  TDistributionAssessor_Measure(PMeasureAttribute =PMeasureAttribute());

  virtual float distributionQuality(TDistClusterNode &node) const;
  virtual float mergeProfit (const TDistClusterNode &, const TDistClusterNode &) const;
};


class TDistributionAssessor_mf : public TDistributionAssessor {
public:
  __REGISTER_CLASS

  float m; //P m for m-estimate

  TDistributionAssessor_mf(const float &am=2.0);

  virtual void setAverage(const float &avg);

  virtual float distributionQuality(TDistClusterNode &node) const;
  virtual float mergeProfit (const TDistClusterNode &, const TDistClusterNode &) const;

  float m_error(const float &sum, const float &sum2, const float &N) const;

private:
  float aprior;
};


class TStopDistributionClustering_noProfit : public TStopDistributionClustering {
public:
  __REGISTER_CLASS
  float minProfitProportion; //P minimal allowable profit proportion

  TStopDistributionClustering_noProfit(const float &minprof=0.0);
  virtual bool operator()(const float &, const TDistProfitQueue &, const TDistClusterNode *clusters) const;
};

class TStopDistributionClustering_noBigChange : public TStopDistributionClustering {
public:
  __REGISTER_CLASS
  virtual bool operator()(const float &, const TDistProfitQueue &, const TDistClusterNode *clusters) const;
};


class TStopDistributionClustering_binary : public TStopDistributionClustering {
public:
  __REGISTER_CLASS
  virtual bool operator()(const float &, const TDistProfitQueue &, const TDistClusterNode *clusters) const;
};


class TStopDistributionClustering_n : public TStopDistributionClustering {
public:
  __REGISTER_CLASS
  int n; //P number of clusters

  TStopDistributionClustering_n(const int & =2);
  virtual bool operator()(const float &, const TDistProfitQueue &, const TDistClusterNode *clusters) const;
};

#endif
