"use client";

import React, { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Upload, FileText, MessageSquare } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useToast } from "@/components/ui/use-toast";

interface Document {
  _id: string;
  name: string;
  created_at: string;
}

const DocumentsPage: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    let isMounted = true;

    const fetchDocuments = async () => {
      try {
        const response = await fetch("http://localhost:8080/api/document/documents");
        if (!response.ok) {
          throw new Error(`Failed to fetch documents: ${response.status}`);
        }

        const data = await response.json();
        let fetchedDocuments: Document[] = [];
        if (Array.isArray(data)) {
          fetchedDocuments = data;
        } else if (Array.isArray(data?.documents)) {
          fetchedDocuments = data.documents;
        }

        if (isMounted) {
          setDocuments(fetchedDocuments);
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown error";
        toast({
          title: "Unable to load documents",
          description: message,
          variant: "destructive",
        });
      }
    };

    fetchDocuments();

    return () => {
      isMounted = false;
    };
  }, [toast]);

  const handleFileUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) {
      return;
    }

    const formData = new FormData();
    Array.from(files).forEach((file) => {
      formData.append("files", file);
    });

    try {
      const response = await fetch("http://localhost:8080/api/document/uploadfile", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload failed with status ${response.status}`);
      }

      let uploadedDocuments: Document[] = [];
      try {
        const data = await response.json();
        if (Array.isArray(data)) {
          uploadedDocuments = data;
        } else if (Array.isArray(data?.documents)) {
          uploadedDocuments = data.documents;
        }
      } catch (jsonError) {
        // If the API doesn't return JSON, fall back to local document metadata.
        uploadedDocuments = Array.from(files).map((file) => ({
          _id: `doc-${Date.now()}-${file.name}`,
          name: file.name,
          created_at: new Date().toLocaleDateString(),
        }));
      }

      if (uploadedDocuments.length === 0) {
        uploadedDocuments = Array.from(files).map((file) => ({
          _id: `doc-${Date.now()}-${file.name}`,
          name: file.name,
          created_at: new Date().toLocaleDateString(),
        }));
      }

      setDocuments((prevDocs) => [...prevDocs, ...uploadedDocuments]);
      toast({
        title: "Upload Successful",
        description: `${files.length} document${files.length > 1 ? "s" : ""} uploaded.`,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      toast({
        title: "Upload Failed",
        description: message,
        variant: "destructive",
      });
    } finally {
      event.target.value = "";
    }
  };

  const handleStartChat = (documentId: string, documentName: string) => {
    navigate(`/chat/${documentId}`, { state: { documentName } });
  };

  return (
    <div className="flex flex-col h-full p-4">
      <h1 className="text-2xl font-bold mb-4">Your Documents</h1>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {documents.map((doc) => (
          <Card key={doc._id}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                {doc.name}
              </CardTitle>
              <FileText className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-lg font-bold truncate">{doc.name}</div>
              <p className="text-xs text-muted-foreground">
                Uploaded on {doc.created_at}
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={() => handleStartChat(doc._id, doc.name)}
              >
                <MessageSquare className="mr-2 h-4 w-4" />
                Start Chat
              </Button>
            </CardContent>
          </Card>
        ))}

        <Card
          className="flex flex-col items-center justify-center p-6 border-2 border-dashed hover:border-primary transition-colors cursor-pointer"
          onClick={handleFileUploadClick}
        >
          <Upload className="h-8 w-8 text-muted-foreground mb-2" />
          <p className="text-sm text-muted-foreground">Upload New Document</p>
          <Button variant="ghost" className="mt-2">Browse Files</Button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            className="hidden"
            accept=".pdf,.doc,.docx,.txt" // Specify accepted file types
            multiple
          />
        </Card>
      </div>
    </div>
  );
};

export default DocumentsPage;