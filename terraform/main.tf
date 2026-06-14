###############################################################################
# RAG Platform – Terraform Infrastructure
# Provisions an EKS cluster, node groups, VPC, and supporting AWS services.
###############################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.13"
    }
  }

  # Remote state — change bucket/key/region to match your account
  backend "s3" {
    bucket         = "your-terraform-state-bucket"
    key            = "rag-platform/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}

###############################################################################
# Variables
###############################################################################

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (staging | production)"
  type        = string
  default     = "production"
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "rag-platform"
}

variable "cluster_version" {
  description = "Kubernetes version"
  type        = string
  default     = "1.30"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "node_instance_types" {
  description = "EC2 instance types for the managed node group"
  type        = list(string)
  default     = ["m6i.xlarge"]
}

variable "node_desired" {
  type    = number
  default = 3
}

variable "node_min" {
  type    = number
  default = 2
}

variable "node_max" {
  type    = number
  default = 10
}

###############################################################################
# Locals
###############################################################################

locals {
  tags = {
    Project     = "rag-platform"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
  azs = slice(data.aws_availability_zones.available.names, 0, 3)
}

###############################################################################
# Data sources
###############################################################################

provider "aws" {
  region = var.aws_region
  default_tags { tags = local.tags }
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

###############################################################################
# VPC
###############################################################################

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.8.1"

  name = "${var.cluster_name}-vpc"
  cidr = var.vpc_cidr

  azs             = local.azs
  private_subnets = [for i, az in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i, az in local.azs : cidrsubnet(var.vpc_cidr, 4, i + 4)]

  enable_nat_gateway     = true
  single_nat_gateway     = var.environment != "production"  # HA NAT in prod
  enable_dns_hostnames   = true
  enable_dns_support     = true

  # Required tags for EKS subnet auto-discovery
  private_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"           = "1"
  }
  public_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/elb"                    = "1"
  }
}

###############################################################################
# EKS Cluster
###############################################################################

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.14.0"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.private_subnets

  # Enable private endpoint; expose public for CI (restrict by CIDR in prod)
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  # Enable EKS add-ons
  cluster_addons = {
    coredns                = { most_recent = true }
    kube-proxy             = { most_recent = true }
    vpc-cni                = { most_recent = true }
    aws-ebs-csi-driver     = { most_recent = true }
  }

  # Managed node group
  eks_managed_node_groups = {
    general = {
      name           = "general"
      instance_types = var.node_instance_types
      desired_size   = var.node_desired
      min_size       = var.node_min
      max_size       = var.node_max
      disk_size      = 100   # GB

      # Use AL2023 for better security defaults
      ami_type = "AL2023_x86_64_STANDARD"

      labels = {
        role = "general"
      }

      # Required for EBS CSI driver
      iam_role_additional_policies = {
        AmazonEBSCSIDriverPolicy = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
      }
    }
  }

  # Enable IRSA (IAM Roles for Service Accounts)
  enable_irsa = true
}

###############################################################################
# ECR — container image registry
###############################################################################

resource "aws_ecr_repository" "rag_platform" {
  name                 = "rag-platform"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true   # automatic vulnerability scanning
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "rag_platform" {
  repository = aws_ecr_repository.rag_platform.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}

###############################################################################
# Outputs
###############################################################################

output "cluster_endpoint" {
  description = "EKS API server endpoint"
  value       = module.eks.cluster_endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64-encoded CA cert for kubectl"
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "ecr_repository_url" {
  description = "ECR URL for docker push"
  value       = aws_ecr_repository.rag_platform.repository_url
}

output "vpc_id" {
  value = module.vpc.vpc_id
}
